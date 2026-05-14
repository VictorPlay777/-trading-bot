"""
Multi-coin scanner bot.
Scans ALL Bybit linear perpetuals, picks top-N by volatility,
trains ML models, and manages positions with trailing TP/SL.
One process instead of N separate bots.
"""
import time, argparse, yaml, pandas as pd, os
from decimal import Decimal, getcontext
from typing import Optional
getcontext().prec = 20
from trader.exchange_demo import Exchange
from ml.features import add_features, FEATURES, market_regime_filter
from ml.labeler import label_regimes
from ml.model import ProbModel
from utils.logging import setup_logging

# ── Config ──────────────────────────────────────────────
TOP_N = 100                # Scan top 100 volatile coins (faster, better quality)
POSITION_SIZE_USDT = 50000.0  # USDT per position
MAX_POSITIONS = 9999          # Unlimited concurrent positions
LEVERAGE = 1
TP_PERCENT = 0.004         # 0.4% take profit (limit reduce-only)
SL_PERCENT = 0.004         # 0.4% stop loss (limit reduce-only)
# Пауза после маркет-входа: демо-API и учёт позиции до выставления TP/SL
POST_ENTRY_BRACKET_DELAY_SEC = 0.45
INTER_BRACKET_DELAY_SEC = 0.12
BRACKET_ORDER_GRACE_SEC = 2.0  # не считать «оба пропали» пока ордера не успели появиться в realtime
ENABLE_BRACKET_CANCEL_SYNC = False  # Отключено: закрытие только по TP/SL, без автокансела
ENABLE_EARLY_MARKET_EXIT = False  # Отключено: без раннего рыночного закрытия по сигналу
PROB_THRESHOLD = 0.51  # Минимальный порог вероятности входа
UNCERTAINTY_THRESHOLD = 0.05  # Skip if prob difference < 5%
MIN_TREND_STRENGTH = 0.3    # Minimum trend strength to trade
HORIZON_BARS = 2           # Predict 2 bars ahead (2 minutes on 1m timeframe)
SCAN_INTERVAL = 60        # Scan tickers every 1 minute (matches 1m timeframe)
CHECK_INTERVAL = 5        # Check positions every 5 seconds
MIN_VOLUME_24H = 0        # No volume filter - include ALL coins

# ── Qty Calculation ──────────────────────────────────────
def calc_qty(usdt: Decimal, price: Decimal, logger=None, symbol: str = None) -> Decimal:
    """
    SINGLE SOURCE OF TRUTH for qty calculation.
    Formula: qty = USDT / price
    
    Args:
        usdt: Target position size in USDT (Decimal) - FIXED, never changes
        price: Current price (Decimal)
        logger: Optional logger for tracing
        symbol: Optional symbol for tracing
    
    Returns:
        Raw qty (Decimal) = usdt / price
    """
    if logger:
        logger.info(f"[QTY TRACE] {symbol or 'UNKNOWN'} usdt_in={usdt}")
        logger.info(f"[QTY TRACE] {symbol or 'UNKNOWN'} price={price}")
    
    if price <= 0:
        if logger:
            logger.error(f"[QTY TRACE] {symbol or 'UNKNOWN'} price <= 0")
        return Decimal('0')
    
    qty = usdt / price
    
    if logger:
        logger.info(f"[QTY TRACE] {symbol or 'UNKNOWN'} qty_raw={qty}")
    
    return qty

def validate_qty(qty: Decimal, instrument_info: dict, logger, symbol: str, skip_max_clamp: bool = False) -> Optional[Decimal]:
    """
    Validate and constrain qty according to Bybit instrument rules.
    Does NOT recalculate qty - only validates and clamps.
    
    Args:
        qty: Calculated qty (Decimal)
        instrument_info: Bybit instrument info dict
        logger: Optional logger for tracing
        symbol: Optional symbol for tracing
    
    Returns:
        Valid qty (Decimal) or None if invalid
    """
    if logger:
        logger.info(f"[QTY TRACE] {symbol or 'UNKNOWN'} validate_qty input: qty={qty}")
    
    if qty <= 0:
        if logger:
            logger.error(f"[QTY TRACE] {symbol or 'UNKNOWN'} qty <= 0")
        return None
    
    lot_filter = instrument_info.get("lotSizeFilter", {})
    qty_step_str = lot_filter.get("qtyStep", "0.001")
    min_qty_str = lot_filter.get("minOrderQty", "0.001")
    max_qty_str = lot_filter.get("maxOrderQty", "1000000000")
    
    try:
        qty_step = Decimal(qty_step_str)
        min_qty = Decimal(min_qty_str)
        max_qty = Decimal(max_qty_str)
    except Exception as e:
        if logger:
            logger.error(f"[QTY TRACE] {symbol or 'UNKNOWN'} failed to parse instrument info: {e}")
        return None
    
    if logger:
        logger.info(f"[QTY TRACE] {symbol or 'UNKNOWN'} max_qty={max_qty}")
        logger.info(f"[QTY TRACE] {symbol or 'UNKNOWN'} min_qty={min_qty}")
        logger.info(f"[QTY TRACE] {symbol or 'UNKNOWN'} qty_step={qty_step}")
    
    # Round DOWN to qtyStep
    qty = (qty // qty_step) * qty_step
    if logger:
        logger.info(f"[QTY TRACE] {symbol or 'UNKNOWN'} after step rounding: qty={qty}")
    
    # Clamp to min/max (skip max clamp for retry mode)
    qty = max(qty, min_qty)
    if logger:
        logger.info(f"[QTY TRACE] {symbol or 'UNKNOWN'} after min clamp: qty={qty}")
    
    # Only apply max clamp if not in retry mode
    if not skip_max_clamp:
        qty = min(qty, max_qty)
        if logger:
            logger.info(f"[QTY TRACE] {symbol or 'UNKNOWN'} after max clamp: qty={qty}")
    else:
        if logger:
            logger.info(f"[QTY TRACE] {symbol or 'UNKNOWN'} skipping max clamp (retry mode)")
    
    # Check if still below minimum after rounding
    if qty < min_qty:
        if logger:
            logger.error(f"[QTY TRACE] {symbol or 'UNKNOWN'} qty < min_qty ({qty} < {min_qty})")
        return None
    
    if logger:
        logger.info(f"[QTY TRACE] {symbol or 'UNKNOWN'} qty_final={qty}")
    
    return qty

# Global storage for latest predictions (symbol -> {'p_up': float, 'p_dn': float, 'signal': str})
LATEST_PREDICTIONS = {}

# После входа: orderId лимитных TP/SL (вторая нога снимается при закрытии позиции или исполнении первой)
PENDING_TP_SL = {}  # symbol -> {'tp': str|None, 'sl': str|None, 'placed_at': float}


def _order_id_from_api_result(result) -> Optional[str]:
    if not result or result.get("retCode") != 0:
        return None
    oid = result.get("result", {}).get("orderId")
    return str(oid) if oid else None


def _cancel_order_id_safe(ex, sym: str, oid: Optional[str], logger) -> None:
    if not oid:
        return
    try:
        r = ex.cancel_order(sym, oid)
        if r.get("retCode") == 0:
            logger.info(f"  >> CANCEL OK {sym} orderId={oid}")
        else:
            logger.debug(f"  >> CANCEL {sym} orderId={oid}: {r.get('retMsg', r)}")
    except Exception as e:
        logger.debug(f"  >> CANCEL {sym} orderId={oid}: {e}")


def _clear_pending_brackets_for_symbol(ex, sym: str, logger) -> None:
    pend = PENDING_TP_SL.pop(sym, None)
    if not pend:
        return
    for key in ("tp", "sl"):
        _cancel_order_id_safe(ex, sym, pend.get(key), logger)


def _open_order_ids_set(ex, sym: str) -> set:
    try:
        r = ex.get_open_orders(sym)
        if r.get("retCode") != 0:
            return set()
        lst = r.get("result", {}).get("list") or []
        return {str(o.get("orderId")) for o in lst if o.get("orderId")}
    except Exception:
        return set()


def _position_size_for_symbol(ex, sym: str) -> float:
    try:
        r = ex.get_positions(sym)
        if r.get("retCode") != 0:
            return 0.0
        for p in r.get("result", {}).get("list", []):
            if p.get("symbol") == sym and float(p.get("size", 0) or 0) > 0:
                return float(p.get("size", 0))
        return 0.0
    except Exception:
        return 0.0


def _reconcile_tp_sl_brackets(ex, logger) -> None:
    """Позиция закрыта → снять оставшийся лимит. Исполнена одна нога → снять вторую."""
    if not ENABLE_BRACKET_CANCEL_SYNC:
        return
    now = time.time()
    for sym in list(PENDING_TP_SL.keys()):
        pend = PENDING_TP_SL.get(sym) or {}
        tp_id = pend.get("tp")
        sl_id = pend.get("sl")
        placed_at = float(pend.get("placed_at") or 0)
        pos_sz = _position_size_for_symbol(ex, sym)
        open_ids = _open_order_ids_set(ex, sym)
        tp_open = bool(tp_id and str(tp_id) in open_ids)
        sl_open = bool(sl_id and str(sl_id) in open_ids)

        if pos_sz <= 0:
            _cancel_order_id_safe(ex, sym, tp_id, logger)
            _cancel_order_id_safe(ex, sym, sl_id, logger)
            PENDING_TP_SL.pop(sym, None)
            continue

        # Пока демо API не показал оба ордера в realtime — не трогаем ноги
        if now - placed_at < BRACKET_ORDER_GRACE_SEC:
            continue

        if tp_open and sl_open:
            continue

        if not tp_open and sl_open and sl_id:
            _cancel_order_id_safe(ex, sym, sl_id, logger)
            PENDING_TP_SL.pop(sym, None)
        elif not sl_open and tp_open and tp_id:
            _cancel_order_id_safe(ex, sym, tp_id, logger)
            PENDING_TP_SL.pop(sym, None)
        elif not tp_open and not sl_open:
            PENDING_TP_SL.pop(sym, None)


def _place_brackets_after_entry(ex, sym: str, position_side: str, qty, entry_price: float, logger) -> None:
    """Два reduce-only лимита TP и SL (±TP_PERCENT). Пауза после маркета под лаг демо API."""
    if ENABLE_BRACKET_CANCEL_SYNC:
        _clear_pending_brackets_for_symbol(ex, sym, logger)
    time.sleep(POST_ENTRY_BRACKET_DELAY_SEC)
    try:
        if position_side == "long":
            tp_price = entry_price * (1 + TP_PERCENT)
            sl_price = entry_price * (1 - SL_PERCENT)
            tp_side = sl_side = "Sell"
        else:
            tp_price = entry_price * (1 - TP_PERCENT)
            sl_price = entry_price * (1 + SL_PERCENT)
            tp_side = sl_side = "Buy"

        r_tp = ex.limit_order(sym, tp_side, qty, tp_price, reduce_only=True)
        time.sleep(INTER_BRACKET_DELAY_SEC)
        # SL ставим как stop-limit (conditional), иначе plain limit исполнится сразу.
        r_sl = ex.stop_limit_close(sym, position_side, qty, sl_price, sl_price)

        tp_oid = _order_id_from_api_result(r_tp)
        sl_oid = _order_id_from_api_result(r_sl)
        if (tp_oid or sl_oid) and ENABLE_BRACKET_CANCEL_SYNC:
            PENDING_TP_SL[sym] = {
                "tp": tp_oid,
                "sl": sl_oid,
                "placed_at": time.time(),
            }
        pct = TP_PERCENT * 100
        logger.info(f"  >> TP LIMIT {sym} @ {tp_price:.6f} (~{pct:.2f}% от входа) orderId={tp_oid}")
        logger.info(f"  >> SL LIMIT {sym} @ {sl_price:.6f} (~{pct:.2f}% от входа) orderId={sl_oid}")
    except Exception as e:
        logger.error(f"  >> FAILED TP/SL brackets for {sym}: {e}")


# ── TP/SL Check Function ────────────────────────────────
def _check_tpsl(ex, tracker, logger, predictions=None):
    """Check early exit for all open positions. TP/SL handled by exchange limit/stop-limit orders.
    predictions: optional dict of latest predictions for trend reversal check"""
    try:
        pos_data = ex.get_positions()
        if pos_data.get('retCode') == 0:
            positions = pos_data.get('result', {}).get('list', [])
            for pos in positions:
                sym = pos.get('symbol', '')
                size = float(pos.get('size', 0))
                if size <= 0:
                    continue
                
                unrealised_pnl = float(pos.get('unrealisedPnl', 0))
                position_value = float(pos.get('positionValue', 0))
                side = pos.get('side', '')
                
                sl_threshold = position_value * 0.02  # 2% loss threshold for early exit
                
                # Check early exit: trend reversed and loss > 2%
                if ENABLE_EARLY_MARKET_EXIT and predictions and sym in predictions:
                    pred = predictions[sym]
                    p_up = pred.get('p_up', 0)
                    p_dn = pred.get('p_dn', 0)
                    signal = pred.get('signal', None)
                    
                    # If position is long but signal became short (strong), and loss > 2%
                    if side == 'Buy' and signal == 'short' and p_dn >= PROB_THRESHOLD and unrealised_pnl <= -sl_threshold:
                        logger.info(f"EARLY EXIT: {sym} trend reversed to short (p_dn={p_dn:.3f}) with loss={unrealised_pnl:.2f}")
                        try:
                            _clear_pending_brackets_for_symbol(ex, sym, logger)
                            ex.market_sell_symbol(sym, size)
                            logger.info(f"Closed {sym} on early exit (trend reversal)")
                            tracker.reset(sym)
                            continue  # Skip to next position
                        except Exception as e:
                            logger.error(f"Failed to close {sym} on early exit: {e}")
                    
                    # If position is short but signal became long (strong), and loss > 2%
                    if side == 'Sell' and signal == 'long' and p_up >= PROB_THRESHOLD and unrealised_pnl <= -sl_threshold:
                        logger.info(f"EARLY EXIT: {sym} trend reversed to long (p_up={p_up:.3f}) with loss={unrealised_pnl:.2f}")
                        try:
                            _clear_pending_brackets_for_symbol(ex, sym, logger)
                            ex.market_buy_symbol(sym, size)
                            logger.info(f"Closed {sym} on early exit (trend reversal)")
                            tracker.reset(sym)
                            continue  # Skip to next position
                        except Exception as e:
                            logger.error(f"Failed to close {sym} on early exit: {e}")
                
                tracker.set_prev_pnl(sym, unrealised_pnl)
    except Exception as e:
        logger.error(f"Error checking positions: {e}")

# ── Helpers ─────────────────────────────────────────────
def get_top_volatile(ex: Exchange, top_n: int = TOP_N, logger=None) -> list:
    """Get top-N most volatile linear perpetuals from Bybit"""
    try:
        tickers = ex.fetch_all_tickers()
        if logger:
            logger.info(f"  Fetched {len(tickers)} tickers from Bybit")
    except Exception as e:
        if logger:
            logger.error(f"  Error fetching tickers: {e}")
        return []
    
    scored = []
    for t in tickers:
        symbol = t.get('symbol', '')
        if not symbol.endswith('USDT'):
            continue
        # Skip if volume too low
        turnover = float(t.get('turnover24h', 0))
        if turnover < MIN_VOLUME_24H:
            continue
        # Volatility = abs(price change % over 24h)
        pct = abs(float(t.get('price24hPcnt', '0')))
        # Also use high-low range as additional volatility measure
        high = float(t.get('highPrice24h', 0))
        low = float(t.get('lowPrice24h', 0))
        last = float(t.get('lastPrice', 1))
        if last > 0:
            hl_range = (high - low) / last
        else:
            hl_range = 0
        # Combined score: 24h change + HL range
        score = pct + hl_range
        scored.append({
            'symbol': symbol,
            'volatility': score,
            'price': last,
            'volume_24h': turnover,
            'pct_24h': pct
        })
    
    # Sort by volatility descending
    scored.sort(key=lambda x: x['volatility'], reverse=True)
    if logger:
        logger.info(f"  {len(scored)} coins passed filters (volume>{MIN_VOLUME_24H/1e6:.0f}M)")
    return scored[:top_n]

# ── Position tracking ──────────────────────────────────
class PositionTracker:
    """Track per-symbol position state for TP/SL"""
    def __init__(self):
        self.prev_pnl = {}       # symbol -> previous unrealisedPnl
        self.breakeven = {}      # symbol -> bool (breakeven triggered)
    
    def reset(self, symbol: str):
        self.prev_pnl.pop(symbol, None)
        self.breakeven.pop(symbol, None)
    
    def get_prev_pnl(self, symbol: str):
        return self.prev_pnl.get(symbol)
    
    def set_prev_pnl(self, symbol: str, pnl: float):
        self.prev_pnl[symbol] = pnl
    
    def is_breakeven(self, symbol: str) -> bool:
        return self.breakeven.get(symbol, False)
    
    def set_breakeven(self, symbol: str, val: bool = True):
        self.breakeven[symbol] = val

# ── Main ────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--top', type=int, default=TOP_N, help='Number of top volatile coins')
    ap.add_argument('--size', type=float, default=POSITION_SIZE_USDT, help='Position size in USDT')
    args = ap.parse_args()
    
    global PROB_THRESHOLD
    cfg = yaml.safe_load(open(args.config, 'r', encoding='utf-8'))
    # В конфиге можно поднять порог выше, но не опускать ниже 0.51
    cfg_threshold = float(cfg.get('prob_threshold', PROB_THRESHOLD))
    PROB_THRESHOLD = max(0.51, cfg_threshold)
    cfg['mode'] = 'live'
    logger = setup_logging(cfg['paths']['logs_dir'])
    
    ex = Exchange(cfg)
    tracker = PositionTracker()
    
    # Models and last candle times per symbol
    models = {}          # symbol -> ProbModel
    last_candle_ts = {}  # symbol -> timestamp
    top_symbols = set()  # current top-N symbols
    all_symbols_seen = set()  # all symbols we've ever tracked
    
    # Set leverage for default symbol at startup
    try:
        ex.set_leverage(LEVERAGE)
        logger.info(f'Leverage set to {LEVERAGE}x')
    except Exception as e:
        logger.warning(f'Could not set leverage: {e}')
    
    last_scan_time = -SCAN_INTERVAL  # Scan immediately on startup
    
    logger.info(f"Scanner started: top={args.top}, size={args.size} USDT, threshold={PROB_THRESHOLD}")
    
    while True:
        now = time.time()
        
        # ── Step 1: Scan tickers periodically ──────────────
        if now - last_scan_time >= SCAN_INTERVAL:
            last_scan_time = now
            logger.info("=" * 60)
            logger.info("SCANNING ALL BYBIT LINEAR PERPETUALS...")
            
            top_list = get_top_volatile(ex, args.top, logger=logger)
            new_top = set(t['symbol'] for t in top_list)
            
            # Log top coins
            for i, t in enumerate(top_list):
                logger.info(f"  #{i+1} {t['symbol']}: vol={t['volatility']:.4f} "
                           f"price={t['price']:.4f} volume={t['volume_24h']/1e6:.1f}M "
                           f"24h_pct={t['pct_24h']*100:.2f}%")
            
            # Symbols that left the top
            left_top = top_symbols - new_top
            if left_top:
                logger.info(f"Left top: {left_top} (positions will stay until TP/SL)")
            
            # New symbols in top
            new_entries = new_top - top_symbols
            if new_entries:
                logger.info(f"New in top: {new_entries}")
            
            top_symbols = new_top
            all_symbols_seen.update(new_top)
            
            # ── Check available capital and position count ───
            total_positions = 0
            used_capital = 0.0
            try:
                all_pos = ex.get_positions()
                if all_pos.get('retCode') == 0:
                    for p in all_pos.get('result', {}).get('list', []):
                        if float(p.get('size', 0)) > 0:
                            total_positions += 1
                            used_capital += float(p.get('positionValue', 0))
            except Exception as e:
                logger.warning(f"Could not check positions: {e}")
            
            available_capital = total_equity - used_capital if 'total_equity' in locals() else 500000.0
            
            logger.info(f"  Positions: {total_positions}/{MAX_POSITIONS}, Used: {used_capital:.0f} USDT, Available: {available_capital:.0f} USDT")
            
            # ── Step 2: Train models for top symbols ───────
            sym_count = 0
            for sym in top_symbols:
                sym_count += 1
                
                # Реакция на исполнение TP/SL и ранний выход — каждые несколько символов
                if sym_count % 3 == 0:
                    _reconcile_tp_sl_brackets(ex, logger)
                    _check_tpsl(ex, tracker, logger, LATEST_PREDICTIONS)
                try:
                    ohlcv = ex.fetch_ohlcv_symbol(sym, limit=600)
                    if len(ohlcv) < 30:
                        logger.info(f"  {sym}: only {len(ohlcv)} candles, skipping")
                        continue
                    
                    latest_ts = ohlcv[-1][0]
                    
                    # Only retrain if new candle
                    if sym not in last_candle_ts or last_candle_ts[sym] != latest_ts:
                        df = pd.DataFrame(ohlcv, columns=['time','open','high','low','close','volume'])
                        df['time'] = pd.to_datetime(df['time'], unit='s')
                        df = df.set_index('time')
                        df = add_features(df)
                        df = label_regimes(df, horizon_bars=HORIZON_BARS, atr_mult=0.5)
                        df_feat = df.dropna(subset=FEATURES+['y'])
                        
                        if len(df_feat) < 50:
                            logger.info(f"  {sym}: only {len(df_feat)} features, skipping")
                            continue
                        
                        # Create or get model
                        if sym not in models:
                            models[sym] = ProbModel()
                        
                        models[sym].fit_partial(df_feat[FEATURES].values, df_feat['y'].values)
                        last_candle_ts[sym] = latest_ts
                        
                        # Get signal
                        row = df_feat.iloc[-1]
                        current_price = row['close']  # Get current price from row
                        proba = models[sym].predict_proba_row(row[FEATURES].values)
                        p_up = proba.get(1, 0.0)
                        p_dn = proba.get(-1, 0.0)
                        
                        # Uncertainty filter: skip if model is not confident
                        prob_diff = abs(p_up - p_dn)
                        if prob_diff < UNCERTAINTY_THRESHOLD:
                            logger.info(f"  {sym}: p_up={p_up:.3f} p_dn={p_dn:.3f} signal=None (uncertain)")
                            signal = None
                        else:
                            signal = None
                            if p_up >= PROB_THRESHOLD:
                                signal = 'long'
                            elif p_dn >= PROB_THRESHOLD:
                                signal = 'short'
                        
                        logger.info(f"  {sym}: p_up={p_up:.3f} p_dn={p_dn:.3f} signal={signal}")
                        
                        # Save prediction for early exit check
                        LATEST_PREDICTIONS[sym] = {'p_up': p_up, 'p_dn': p_dn, 'signal': signal}
                        
                        # ── Step 3: Open position if signal ──
                        if signal:
                            # Market regime filter: check if market has trend
                            if not market_regime_filter(df_feat, min_trend_strength=MIN_TREND_STRENGTH):
                                logger.info(f"  >> SKIP {sym}: flat market (trend strength < {MIN_TREND_STRENGTH})")
                                continue
                            
                            # Double filter: ML + market conditions
                            # Trend confirmation: EMA20 > EMA50 for long, EMA20 < EMA50 for short
                            ema20 = df_feat['ema_20'].iloc[-1] if 'ema_20' in df_feat.columns else df_feat['ema_21'].iloc[-1]
                            ema50 = df_feat['ema_50'].iloc[-1]
                            
                            if signal == 'long' and ema20 <= ema50:
                                logger.info(f"  >> SKIP {sym}: trend not confirmed for long (EMA20={ema20:.6f} <= EMA50={ema50:.6f})")
                                continue
                            elif signal == 'short' and ema20 >= ema50:
                                logger.info(f"  >> SKIP {sym}: trend not confirmed for short (EMA20={ema20:.6f} >= EMA50={ema50:.6f})")
                                continue
                            
                            # Volume confirmation: volume > SMA(volume, 20)
                            volume_ratio = df_feat['volume_ratio'].iloc[-1] if 'volume_ratio' in df_feat.columns else 1.0
                            if volume_ratio < 1.0:
                                logger.info(f"  >> SKIP {sym}: low volume (ratio={volume_ratio:.2f})")
                                continue
                            
                            # Check limits
                            if total_positions >= MAX_POSITIONS:
                                logger.info(f"  >> SKIP {sym}: max positions reached ({MAX_POSITIONS})")
                                continue
                            
                            # Check if we have enough capital for this position
                            if available_capital < args.size:
                                logger.info(f"  >> SKIP {sym}: not enough capital (need {args.size}, have {available_capital:.0f})")
                                continue
                            
                            # Check if we have enough margin for max possible position
                            # Calculate required margin for max possible position
                            info = ex.get_symbol_info(sym)
                            if info:
                                lot_filter = info.get("lotSizeFilter", {})
                                max_qty_str = lot_filter.get("maxOrderQty", "1000000000")
                            else:
                                max_qty_str = "1000000000"
                            
                            max_qty_decimal = Decimal(str(max_qty_str))
                            max_usdt_possible = max_qty_decimal * Decimal(str(current_price))
                            # Skip balance check - Bybit will reject if insufficient margin
                            
                            # Check if we already have a position for this symbol
                            pos_data = ex.get_positions()
                            has_position = False
                            if pos_data.get('retCode') == 0:
                                for p in pos_data.get('result', {}).get('list', []):
                                    if p.get('symbol') == sym and float(p.get('size', 0)) > 0:
                                        has_position = True
                                        break
                            
                            if not has_position:
                                # Update counters
                                total_positions += 1
                                available_capital -= args.size
                                current_price = float(row['close'])
                                target_size = args.size
                                
                                # Calculate qty using SINGLE SOURCE OF TRUTH
                                info = ex.get_symbol_info(sym)
                                if not info:
                                    logger.info(f"  >> SKIP {sym}: no instrument info")
                                    continue
                                
                                # Extract max_qty from instrument info
                                lot_filter = info.get("lotSizeFilter", {})
                                # For market orders, use maxMktOrderQty if available
                                max_qty_str = lot_filter.get("maxMktOrderQty") or lot_filter.get("maxOrderQty", "1000000000")
                                
                                # Calculate max USDT possible with this instrument
                                max_qty_decimal = Decimal(str(max_qty_str))
                                max_usdt_possible = max_qty_decimal * Decimal(str(current_price))
                                
                                # Use smaller of target size or max possible
                                actual_usdt = min(Decimal(str(target_size)), max_usdt_possible)
                                
                                logger.info(f"  >> {sym}: target={target_size:.0f} USDT, max_possible={max_usdt_possible:.0f} USDT, using={actual_usdt:.0f} USDT")
                                
                                # Step 1: Calculate qty = USDT / price (ONLY formula)
                                raw_qty = calc_qty(
                                    usdt=actual_usdt,
                                    price=Decimal(str(current_price)),
                                    logger=logger,
                                    symbol=sym
                                )
                                
                                # Step 2: Validate and constrain qty (no recalculation)
                                qty = validate_qty(raw_qty, info, logger=logger, symbol=sym)
                                
                                if qty is None:
                                    logger.info(f"  >> SKIP {sym}: qty validation failed or below minimum")
                                    continue
                                
                                qty_str = str(qty)
                                qty_decimal = qty
                                
                                # Debug log before order
                                max_qty_str = info.get("lotSizeFilter", {}).get("maxOrderQty", "unknown")
                                min_qty_str = info.get("lotSizeFilter", {}).get("minOrderQty", "unknown")
                                step_str = info.get("lotSizeFilter", {}).get("qtyStep", "unknown")
                                logger.info(f"  >> ORDER: {sym} price={current_price:.6f} usdt={target_size:.0f} qty={qty_str} max_qty={max_qty_str} min_qty={min_qty_str} step={step_str}")
                                
                                # CRITICAL: Final trace before API
                                logger.info(f"[QTY TRACE] {sym} FINAL before API: qty={qty_decimal} type={type(qty_decimal)}")
                                logger.error(f"[FINAL DEBUG] {sym} type={type(qty_decimal)} value={repr(qty_decimal)} id={id(qty_decimal)}")
                                
                                # Detect float/int conversion attempt
                                if not isinstance(qty_decimal, Decimal):
                                    logger.error(f"[QTY TRACE] {sym} CRITICAL: qty is NOT Decimal! type={type(qty_decimal)}")
                                    continue
                                
                                # Set leverage for this symbol before opening position
                                try:
                                    ex.set_leverage(LEVERAGE)
                                except Exception as e:
                                    logger.warning(f"  Could not set leverage for {sym}: {e}")
                                
                                # Place order
                                order = {
                                    'symbol': sym,
                                    'signal': signal,
                                    'qty': qty,
                                    'usdt': target_size,
                                    'price': current_price,
                                    'timestamp': time.time()
                                }
                                
                                try:
                                    # NORMAL LOGIC: ML says long -> open long, ML says short -> open short
                                    if signal == 'long':
                                        result = ex.market_buy_symbol(sym, qty)  # Normal: long -> long
                                        actual_signal = 'long'
                                    else:
                                        result = ex.market_sell_symbol(sym, qty)   # Normal: short -> short
                                        actual_signal = 'short'
                                    
                                    # Success
                                    qty_str = str(qty)
                                    actual_value = float(qty_decimal) * current_price
                                    logger.info(f"  >> OPENED {actual_signal} {sym} (ML: {signal}) qty={qty_str} value={actual_value:.2f} USDT")
                                    _place_brackets_after_entry(ex, sym, actual_signal, qty, float(current_price), logger)
                                    tracker.reset(sym)
                                except Exception as e:
                                    err_str = str(e)
                                    # Parse Bybit error for qty limits
                                    if "max_qty:" in err_str:
                                        import re
                                        match = re.search(r'max_qty:(\d+)', err_str)
                                        if match:
                                            api_max_qty = Decimal(match.group(1))
                                            logger.info(f"  >> {sym}: API max_qty={api_max_qty:.0f}, retrying with 95% of limit")
                                            # Use 95% of API max_qty but don't exceed instrument max_qty and safe limits
                                            # Use maxMktOrderQty for market orders
                                            lot_filter = info.get("lotSizeFilter", {})
                                            instrument_max_qty = Decimal(lot_filter.get("maxMktOrderQty") or lot_filter.get("maxOrderQty", "0"))
                                            api_retry_qty = api_max_qty * Decimal('0.95')
                                            # Use 95% of API max_qty, capped at instrument max_qty
                                            retry_qty = min(api_retry_qty, instrument_max_qty)
                                            logger.info(f"  [QTY TRACE] {sym} retry: API limit={api_retry_qty:.0f}, instrument limit={instrument_max_qty:.0f}, using={retry_qty:.0f}")
                                            
                                            # Re-validate retry qty (but don't clamp to instrument max_qty)
                                            retry_qty_final = validate_qty(retry_qty, info, logger=logger, symbol=sym, skip_max_clamp=True)
                                            if retry_qty_final:
                                                logger.info(f"  [QTY TRACE] {sym} retry validated: qty={retry_qty_final}")
                                                # Update the order with retry qty
                                                order['qty'] = retry_qty_final
                                                order['usdt'] = float(retry_qty_final) * current_price
                                                # Retry the order
                                                try:
                                                    if signal == 'long':
                                                        result = ex.market_buy_symbol(sym, retry_qty_final)
                                                    else:
                                                        result = ex.market_sell_symbol(sym, retry_qty_final)
                                                    
                                                    qty_str = str(retry_qty_final)
                                                    actual_value = float(retry_qty_final) * current_price
                                                    logger.info(f"  >> OPENED {signal} {sym} qty={qty_str} value={actual_value:.2f} USDT (retry)")
                                                    _place_brackets_after_entry(
                                                        ex, sym, signal, retry_qty_final, float(current_price), logger
                                                    )
                                                    tracker.reset(sym)
                                                except Exception as e2:
                                                    logger.error(f"  >> FAILED to open {signal} {sym} (retry): {e2}")
                                                    continue
                                    # Parse position limit error (110090)
                                    elif "exceed the max. limit" in err_str or "110090" in err_str:
                                        logger.info(f"  >> Order rejected: position limit exceeded")
                                        # Retry: clamp qty to max_qty * 0.95 (USDT stays FIXED)
                                        # Use maxMktOrderQty for market orders
                                        lot_filter = info.get("lotSizeFilter", {})
                                        instrument_max_qty = Decimal(lot_filter.get("maxMktOrderQty") or lot_filter.get("maxOrderQty", "0"))
                                        api_retry_qty = Decimal(match.group(1)) * Decimal('0.95')
                                        retry_qty = min(api_retry_qty, instrument_max_qty)
                                        logger.info(f"  [QTY TRACE] {sym} retry: API limit={api_retry_qty:.0f}, instrument limit={instrument_max_qty:.0f}, using={retry_qty:.0f}")
                                        # Re-validate clamped qty
                                        retry_qty_final = validate_qty(retry_qty, info, logger=logger, symbol=sym)
                                        if retry_qty_final:
                                            # Retry the order
                                            try:
                                                if signal == 'long':
                                                    result = ex.market_buy_symbol(sym, retry_qty_final)
                                                else:
                                                    result = ex.market_sell_symbol(sym, retry_qty_final)
                                                
                                                qty_str = str(retry_qty_final)
                                                actual_value = float(retry_qty_final) * current_price
                                                logger.info(f"  >> OPENED {signal} {sym} qty={qty_str} value={actual_value:.2f} USDT (position limit retry)")
                                                _place_brackets_after_entry(
                                                    ex, sym, signal, retry_qty_final, float(current_price), logger
                                                )
                                                tracker.reset(sym)
                                            except Exception as e2:
                                                logger.error(f"  >> FAILED to open {signal} {sym} (position limit retry): {e2}")
                                                continue
                                    else:
                                        logger.error(f"  >> FAILED to open {signal} {sym}: {err_str}")
                                        continue
                
                except Exception as e:
                    logger.error(f"  Error processing {sym}: {e}")
            
            logger.info("=" * 60)
        
        # ── Step 4: Снять вторую ногу TP/SL после исполнения первой / закрытия позиции
        _reconcile_tp_sl_brackets(ex, logger)
        # ── Step 5: Check TP/SL for ALL open positions ────
        _check_tpsl(ex, tracker, logger, LATEST_PREDICTIONS)
        
        # ── Step 6: Log equity ────────────────────────────
        try:
            balance_data = ex.get_wallet_balance()
            if balance_data.get('retCode') == 0:
                accounts = balance_data.get('result', {}).get('list', [])
                if accounts:
                    total_equity = float(accounts[0].get('totalEquity', 0))
                    logger.info(f"Equity: {total_equity:.2f} USDT")
        except:
            pass
        
        time.sleep(CHECK_INTERVAL)

if __name__ == '__main__':
    main()
