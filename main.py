"""
Main Trading Bot - Simple Synchronous Version
"""
import sys
import time
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict

from config import trading_config, regime_config, strategy_config, risk_config, api_config
from logger import setup_logger, get_logger, log_event
from api_client import BybitClient
from market_data import MarketDataManager
from indicators import calculate_all_indicators
from regime_detector import regime_detector
from strategy import strategy, SignalType
from risk_manager import risk_manager, format_quantity
from portfolio import portfolio

logger = setup_logger()


class TradingBot:
    """
    Main trading bot orchestrator - SYNC version
    """
    
    def __init__(self):
        self.api = BybitClient()
        self.market_data = MarketDataManager(self.api)
        self.symbols = trading_config.symbols  # List of symbols for multi-symbol trading
        self.interval = trading_config.main_timeframe
        self._running = False
        self._paused = False  # Pause state
        self._last_check_time: Optional[datetime] = None
        self._check_interval_seconds = 5  # Check every 5 seconds (within API limits)
        self._current_positions = {}  # Track positions per symbol: {symbol: "long"/"short"/None} - populated from API each run
        self._current_symbol_index = 0  # For cycling through symbols
        self._pending_signal = None
        self._last_config_reload: Optional[datetime] = None
        self._config_reload_interval = 30  # Reload config every 30 seconds
        self._instruments_info = {}  # Cache instruments info: {symbol: {min_qty, max_qty, qty_step}}

        # Smart filter tracking - stateless for GitHub Actions
        self._last_trade_time: Optional[datetime] = None  # Track last trade time for delay
        self._consecutive_sl_count = 0  # Track consecutive stop losses
        self._loss_streak_pause_until: Optional[datetime] = None  # Pause end time
    
    def initialize(self):
        """Initialize bot - connect, set leverage, sync positions from API"""
        logger.info("=" * 60)
        logger.info("INITIALIZING TRADING BOT")
        logger.info("=" * 60)
        logger.info(f"Exchange: Bybit Testnet")
        logger.info(f"Symbols: {', '.join(self.symbols)}")
        logger.info(f"Timeframe: {self.interval}m")
        logger.info(f"Max Positions: {trading_config.max_positions}")
        logger.info("-" * 60)

        # Initialize positions tracking for each symbol
        for symbol in self.symbols:
            self._current_positions[symbol] = None

        # Test API connection
        try:
            balance = self.api.get_wallet_balance()
            usdt_balance = 0.0
            for account in balance.get("result", {}).get("list", []):
                for coin in account.get("coin", []):
                    if coin.get("coin") == "USDT":
                        usdt_balance = float(coin.get("walletBalance", 0))

            portfolio.set_account_balance(usdt_balance)
            logger.info(f"Account Balance: {usdt_balance:.2f} USDT")

        except Exception as e:
            logger.error(f"Failed to connect to API: {e}")
            raise

        # Load instruments info for all symbols (lot size requirements)
        self._load_instruments_info()

        # Set leverage for all symbols (use default leverage from config)
        for symbol in self.symbols:
            try:
                if symbol in self._instruments_info:
                    max_lev = self._instruments_info[symbol].get("max_leverage", trading_config.default_leverage)
                else:
                    max_lev = trading_config.symbol_max_leverage.get(symbol, trading_config.default_leverage)

                # Use default leverage from config, capped at symbol max
                target_leverage = min(trading_config.default_leverage, max_lev)

                self.api.set_leverage(symbol, target_leverage, target_leverage)
                logger.info(f"Leverage set to {target_leverage}x for {symbol} (config default: {trading_config.default_leverage}x)")
            except Exception as e:
                logger.warning(f"Failed to set leverage for {symbol}: {e}")

        # Sync positions from API for stateless operation
        self._sync_positions()

        # Load initial market data for all symbols
        for symbol in self.symbols:
            try:
                self.market_data.refresh_cache(symbol)
                logger.info(f"Market data loaded for {symbol}")
            except Exception as e:
                logger.warning(f"Failed to load market data for {symbol}: {e}")

        # Open EMA-based positions for symbols that don't have positions
        symbols_without_positions = [s for s, pos in self._current_positions.items() if pos is None]
        if symbols_without_positions:
            logger.info(f"🎲 Opening EMA-based positions for {len(symbols_without_positions)} symbols without positions: {', '.join(symbols_without_positions)}")
            self._open_ema_positions_for_symbols(symbols_without_positions)

        logger.info("=" * 60)
        logger.info("BOT READY")
        logger.info("=" * 60)

    def _load_instruments_info(self):
        """Load instruments info (lot size requirements) for all symbols"""
        logger.info("Loading instruments info...")
        try:
            # Load instruments info for each symbol individually
            for symbol in self.symbols:
                try:
                    instruments = self.api.get_instruments_info(symbol=symbol)
                    if instruments:
                        inst = instruments[0]
                        lot_size_filter = inst.get("lotSizeFilter", {})
                        price_filter = inst.get("priceFilter", {})
                        # Try different field names for contract multiplier
                        contract_multiplier = float(inst.get("contractMultipler", inst.get("contractMultiplier", inst.get("multiplier", "1"))))
                        price_tick_size = float(price_filter.get("tickSize", "0.01"))
                        # Parse max_leverage - API may return scaled values (e.g., 7500 for 75x)
                        max_lev_str = inst.get("leverageFilter", {}).get("maxLeverage", "50")
                        max_lev = int(float(max_lev_str))
                        if max_lev > 1000:
                            max_lev = max_lev // 100  # Scale down if API returns 7500 instead of 75
                        
                        self._instruments_info[symbol] = {
                            "min_qty": float(lot_size_filter.get("minOrderQty", "0")),
                            "max_qty": float(lot_size_filter.get("maxOrderQty", "999999999")),
                            "max_mkt_qty": float(lot_size_filter.get("maxMktOrderQty", "999999999")),
                            "qty_step": float(lot_size_filter.get("qtyStep", "0.001")),
                            "contract_multiplier": contract_multiplier,
                            "price_tick_size": price_tick_size,
                            "max_leverage": max_lev
                        }
                        logger.info(f"Instruments info loaded for {symbol}: min={self._instruments_info[symbol]['min_qty']}, max={self._instruments_info[symbol]['max_qty']}, step={self._instruments_info[symbol]['qty_step']}, contract_multiplier={contract_multiplier}, price_tick_size={price_tick_size}, max_leverage={self._instruments_info[symbol]['max_leverage']}")
                    else:
                        logger.warning(f"No instruments info returned for {symbol}")
                except Exception as e:
                    logger.warning(f"Failed to load instruments info for {symbol}: {e}")
        except Exception as e:
            logger.warning(f"Failed to load instruments info: {e}")

    def _format_price(self, symbol: str, price: float) -> float:
        """Format price according to symbol's price tick size requirements"""
        if symbol not in self._instruments_info:
            logger.warning(f"No instruments info for {symbol}, using price as-is")
            return price

        info = self._instruments_info[symbol]
        price_tick_size = info.get("price_tick_size", 0.01)

        # Round to nearest tick size
        formatted_price = round(price / price_tick_size) * price_tick_size

        return formatted_price

    def _is_atr_valid(self, symbol: str) -> tuple[bool, float, str]:
        """Check if ATR is above threshold (anti-sideways filter)"""
        if not strategy_config.atr_filter_enabled:
            return True, 0.0, "ATR filter disabled"

        try:
            timeframe = strategy_config.atr_timeframe
            klines = self.api.get_klines(symbol, timeframe, limit=50)
            if not klines or len(klines) < strategy_config.atr_period:
                return True, 0.0, "Insufficient data for ATR"

            # Calculate ATR
            highs = [float(k[2]) for k in klines]
            lows = [float(k[3]) for k in klines]
            closes = [float(k[4]) for k in klines]

            atr = self._calculate_atr(highs, lows, closes, strategy_config.atr_period)
            atr_pct = atr / closes[-1] if closes[-1] > 0 else 0

            min_threshold = strategy_config.atr_min_threshold_pct
            if atr_pct < min_threshold:
                return False, atr_pct, f"ATR too low: {atr_pct:.4%} < {min_threshold:.4%}"

            return True, atr_pct, f"ATR valid: {atr_pct:.4%}"
        except Exception as e:
            logger.warning(f"Error checking ATR for {symbol}: {e}")
            return True, 0.0, "ATR check error (allowing trade)"

    def _calculate_atr(self, highs, lows, closes, period: int) -> float:
        """Calculate ATR using True Range"""
        tr_values = []
        for i in range(1, len(highs)):
            high = highs[i]
            low = lows[i]
            prev_close = closes[i - 1]

            tr1 = high - low
            tr2 = abs(high - prev_close)
            tr3 = abs(low - prev_close)
            tr = max(tr1, tr2, tr3)
            tr_values.append(tr)

        if len(tr_values) < period:
            return sum(tr_values) / len(tr_values) if tr_values else 0

        return sum(tr_values[-period:]) / period

    def _is_adx_valid(self, symbol: str) -> tuple[bool, float, str]:
        """Check if ADX is above threshold (trend strength filter)"""
        if not strategy_config.adx_filter_enabled:
            return True, 0.0, "ADX filter disabled"

        try:
            timeframe = strategy_config.adx_timeframe
            klines = self.api.get_klines(symbol, timeframe, limit=50)
            if not klines or len(klines) < strategy_config.adx_period + 1:
                return True, 0.0, "Insufficient data for ADX"

            highs = [float(k[2]) for k in klines]
            lows = [float(k[3]) for k in klines]
            closes = [float(k[4]) for k in klines]

            adx = self._calculate_adx(highs, lows, closes, strategy_config.adx_period)
            min_threshold = strategy_config.adx_min_threshold

            if adx < min_threshold:
                return False, adx, f"ADX too low (flat market): {adx:.2f} < {min_threshold}"

            return True, adx, f"ADX valid: {adx:.2f}"
        except Exception as e:
            logger.warning(f"Error checking ADX for {symbol}: {e}")
            return True, 0.0, "ADX check error (allowing trade)"

    def _calculate_adx(self, highs, lows, closes, period: int) -> float:
        """Calculate ADX indicator"""
        # Simplified ADX calculation
        plus_dm = []
        minus_dm = []
        tr = []

        for i in range(1, len(highs)):
            high_diff = highs[i] - highs[i - 1]
            low_diff = lows[i - 1] - lows[i]

            if high_diff > low_diff and high_diff > 0:
                plus_dm.append(high_diff)
            else:
                plus_dm.append(0)

            if low_diff > high_diff and low_diff > 0:
                minus_dm.append(low_diff)
            else:
                minus_dm.append(0)

            tr1 = highs[i] - lows[i]
            tr2 = abs(highs[i] - closes[i - 1])
            tr3 = abs(lows[i] - closes[i - 1])
            tr.append(max(tr1, tr2, tr3))

        if len(tr) < period:
            return 0

        # Smoothed values
        atr = sum(tr[:period]) / period
        plus_di = sum(plus_dm[:period]) / atr * 100 if atr > 0 else 0
        minus_di = sum(minus_dm[:period]) / atr * 100 if atr > 0 else 0

        dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0

        return dx  # Simplified ADX (using current DX instead of smoothed ADX)

    def _is_ema_trending(self, symbol: str) -> tuple[bool, str]:
        """Check if EMAs show clear trend (not sideways)"""
        if not strategy_config.ema_filter_enabled:
            return True, "EMA filter disabled"

        try:
            timeframe = strategy_config.ema_timeframe
            klines = self.api.get_klines(symbol, timeframe, limit=250)
            if not klines or len(klines) < strategy_config.ema_slow_period:
                return True, "Insufficient data for EMA"

            closes = [float(k[4]) for k in klines]

            # Calculate EMAs
            ema_fast = self._calculate_ema(closes, strategy_config.ema_fast_period)
            ema_slow = self._calculate_ema(closes, strategy_config.ema_slow_period)

            # Check distance
            distance_pct = abs(ema_fast - ema_slow) / ema_slow if ema_slow > 0 else 0
            min_distance = strategy_config.ema_min_distance_pct

            if distance_pct < min_distance:
                return False, f"EMAs too close (sideways): {distance_pct:.4%} < {min_distance:.4%}"

            return True, f"EMA trend valid: {distance_pct:.4%}"
        except Exception as e:
            logger.warning(f"Error checking EMA for {symbol}: {e}")
            return True, "EMA check error (allowing trade)"

    def _calculate_ema(self, data, period: int) -> float:
        """Calculate EMA"""
        if len(data) < period:
            return data[-1] if data else 0

        multiplier = 2 / (period + 1)
        ema = sum(data[:period]) / period

        for price in data[period:]:
            ema = (price - ema) * multiplier + ema

        return ema

    def _is_volume_valid(self, symbol: str) -> tuple[bool, str]:
        """Check if current volume is above moving average"""
        if not strategy_config.volume_filter_enabled:
            return True, "Volume filter disabled"

        try:
            timeframe = strategy_config.volume_timeframe
            klines = self.api.get_klines(symbol, timeframe, limit=50)
            if not klines or len(klines) < strategy_config.volume_ma_period:
                return True, "Insufficient data for volume"

            volumes = [float(k[5]) for k in klines]
            current_volume = volumes[-1]
            ma_volume = sum(volumes[-strategy_config.volume_ma_period:]) / strategy_config.volume_ma_period

            min_ratio = strategy_config.volume_min_ratio
            ratio = current_volume / ma_volume if ma_volume > 0 else 0

            if ratio < min_ratio:
                return False, f"Volume too low: {ratio:.2f}x < {min_ratio:.2f}x MA"

            return True, f"Volume valid: {ratio:.2f}x MA"
        except Exception as e:
            logger.warning(f"Error checking volume for {symbol}: {e}")
            return True, "Volume check error (allowing trade)"

    def _should_trade(self, symbol: str) -> tuple[bool, str]:
        """Check if trading conditions are met (combines all filters)"""
        reasons = []

        # Check ATR
        atr_valid, atr_val, atr_msg = self._is_atr_valid(symbol)
        if not atr_valid:
            reasons.append(atr_msg)

        # Check ADX
        adx_valid, adx_val, adx_msg = self._is_adx_valid(symbol)
        if not adx_valid:
            reasons.append(adx_msg)

        # Check EMA
        ema_valid, ema_msg = self._is_ema_trending(symbol)
        if not ema_valid:
            reasons.append(ema_msg)

        # Check volume
        volume_valid, volume_msg = self._is_volume_valid(symbol)
        if not volume_valid:
            reasons.append(volume_msg)

        # Check loss streak pause
        if self._loss_streak_pause_until:
            if datetime.utcnow() < self._loss_streak_pause_until:
                remaining = (self._loss_streak_pause_until - datetime.utcnow()).total_seconds()
                reasons.append(f"Loss streak pause: {int(remaining/60)} min remaining")
            else:
                # Pause expired, reset
                self._loss_streak_pause_until = None
                self._consecutive_sl_count = 0
                logger.info("Loss streak pause expired, resuming trading")

        # Check trade delay
        if self._last_trade_time:
            from config import execution_config
            delay_sec = (datetime.utcnow() - self._last_trade_time).total_seconds()
            if delay_sec < execution_config.min_trade_delay_sec:
                remaining = execution_config.min_trade_delay_sec - delay_sec
                reasons.append(f"Trade delay: {remaining:.1f} sec remaining")

        if reasons:
            return False, "; ".join(reasons)

        return True, "All filters passed"

    def _should_reverse(self, symbol: str, old_direction: str) -> bool:
        """Check if reversal is allowed (only if ADX > threshold)"""
        if not strategy_config.adx_filter_enabled:
            return True

        try:
            _, adx_val, _ = self._is_adx_valid(symbol)
            min_threshold = strategy_config.adx_reverse_threshold

            if adx_val < min_threshold:
                logger.info(f"Reversal blocked for {symbol}: ADX {adx_val:.2f} < {min_threshold} (flat market)")
                return False

            logger.info(f"Reversal allowed for {symbol}: ADX {adx_val:.2f} >= {min_threshold}")
            return True
        except Exception as e:
            logger.warning(f"Error checking reversal condition for {symbol}: {e}")
            return True  # Allow on error

    def _record_sl(self):
        """Record a stop loss for loss streak tracking"""
        self._consecutive_sl_count += 1
        logger.warning(f"Consecutive SL count: {self._consecutive_sl_count}/{risk_config.max_consecutive_sl}")

        if self._consecutive_sl_count >= risk_config.max_consecutive_sl:
            pause_minutes = risk_config.loss_streak_pause_minutes
            self._loss_streak_pause_until = datetime.utcnow() + timedelta(minutes=pause_minutes)
            logger.warning(f"Loss streak reached {self._consecutive_sl_count}, pausing for {pause_minutes} minutes")

    def _record_tp(self):
        """Reset consecutive SL count on TP (successful trade)"""
        if self._consecutive_sl_count > 0:
            logger.info(f"TP hit, resetting consecutive SL count from {self._consecutive_sl_count}")
            self._consecutive_sl_count = 0

    def _format_qty(self, symbol: str, qty: float, is_market_order: bool = False) -> float:
        """Format qty according to symbol's lot size requirements"""
        if symbol not in self._instruments_info:
            logger.warning(f"No instruments info for {symbol}, using qty as-is")
            return qty

        info = self._instruments_info[symbol]
        min_qty = info["min_qty"]
        max_qty = info["max_qty"]
        max_mkt_qty = info.get("max_mkt_qty", max_qty)
        qty_step = info["qty_step"]
        contract_multiplier = info.get("contract_multiplier", 1.0)

        logger.info(f"_format_qty {symbol}: input_qty={qty}, min_qty={min_qty}, max_qty={max_qty}, max_mkt_qty={max_mkt_qty}, qty_step={qty_step}, contract_multiplier={contract_multiplier}, is_market_order={is_market_order}")

        # Divide by contract multiplier if > 1
        if contract_multiplier > 1:
            qty = qty / contract_multiplier
            logger.info(f"Adjusted qty for {symbol}: divided by contract_multiplier {contract_multiplier}, new_qty={qty}")

        # Round to nearest qty_step
        formatted_qty = round(qty / qty_step) * qty_step
        logger.info(f"Rounded qty for {symbol}: {formatted_qty}")

        # Use max_mkt_qty for market orders, max_qty for limit orders
        effective_max = max_mkt_qty if is_market_order else max_qty

        # Ensure within bounds
        if formatted_qty < min_qty:
            formatted_qty = min_qty
            logger.warning(f"Qty {qty} rounded up to min_qty {min_qty} for {symbol}")
        elif formatted_qty > effective_max:
            # Use 80% of effective max to be safe
            formatted_qty = effective_max * 0.8
            # Round to step again
            formatted_qty = round(formatted_qty / qty_step) * qty_step
            logger.warning(f"Qty {qty} exceeds {effective_max} for {symbol} (market order: {is_market_order}), using {formatted_qty} (80% of limit)")

        # Final rounding to avoid floating point precision issues
        formatted_qty = round(formatted_qty, 8)
        logger.info(f"_format_qty {symbol}: output_qty={formatted_qty}")
        return formatted_qty

    def _place_order_with_adaptive_qty(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: float,
        stop_loss: float,
        take_profit: float,
        market_unit: str = None,
        max_retries: int = 5
    ) -> Dict:
        """Place order with adaptive qty retry - reduces qty by 50% on each failure"""
        current_qty = qty
        for attempt in range(max_retries):
            try:
                # Round qty to avoid floating point precision issues
                rounded_qty = round(current_qty, 8)
                result = self.api.place_order(
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    qty=rounded_qty,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    market_unit=market_unit
                )
                if result.get("retCode") == 0:
                    return result
                else:
                    error_msg = result.get("retMsg", "")
                    if "Qty invalid" in error_msg or "exceeds maximum limit" in error_msg:
                        if attempt < max_retries - 1:
                            current_qty = current_qty * 0.5
                            logger.warning(f"Qty invalid for {symbol} (attempt {attempt + 1}/{max_retries}), retrying with 50% less qty: {current_qty}")
                            continue
                    return result
            except Exception as e:
                error_msg = str(e)
                if "Qty invalid" in error_msg or "exceeds maximum limit" in error_msg:
                    if attempt < max_retries - 1:
                        current_qty = current_qty * 0.5
                        logger.warning(f"Qty invalid for {symbol} (attempt {attempt + 1}/{max_retries}), retrying with 50% less qty: {current_qty}")
                        continue
                raise
        return {"retCode": -1, "retMsg": "Max retries exceeded"}
    
    def _sync_positions(self):
        """Sync position state with exchange for all symbols"""
        for symbol in self.symbols:
            actual = self.api.check_position_state(symbol)

            if actual:
                self._current_positions[symbol] = "long" if actual["side"] == "Buy" else "short"
                logger.info(f"Position synced for {symbol}: {self._current_positions[symbol]}")

                # Check for partial exit and trailing stop
                self._check_tp_sl_actions(symbol, actual)
            else:
                # Position closed on exchange - close in portfolio
                if self._current_positions[symbol] is not None:
                    logger.info(f"Position closed on exchange for {symbol}")
                    pos = portfolio.get_position(symbol)
                    if pos:
                        # Get exit price from position info
                        exit_price = actual.get("avg_price") if actual else 0
                        # If avg_price is empty, try mark_price or last_price
                        if not exit_price or exit_price == "" or exit_price == 0:
                            exit_price = actual.get("mark_price", 0) if actual else 0
                        if not exit_price or exit_price == "" or exit_price == 0:
                            exit_price = actual.get("last_price", 0) if actual else 0
                        # Fallback to entry price if still 0
                        if not exit_price or exit_price == 0:
                            exit_price = getattr(pos, 'entry_price', 0)

                        # Check if this was a Stop Loss or Take Profit closure
                        exit_reason = "TP/SL from exchange"
                        was_sl = False
                        was_tp = False
                        if pos.stop_loss > 0:
                            # For long: SL is below entry, check if exit price is near SL
                            if pos.direction == "long" and exit_price <= pos.stop_loss * 1.01:
                                was_sl = True
                                exit_reason = "Stop Loss triggered"
                            # For short: SL is above entry, check if exit price is near SL
                            elif pos.direction == "short" and exit_price >= pos.stop_loss * 0.99:
                                was_sl = True
                                exit_reason = "Stop Loss triggered"

                        if pos.take_profit_1 > 0 and not was_sl:
                            # For long: TP is above entry, check if exit price is near TP
                            if pos.direction == "long" and exit_price >= pos.take_profit_1 * 0.99:
                                was_tp = True
                                exit_reason = "Take Profit triggered"
                            # For short: TP is below entry, check if exit price is near TP
                            elif pos.direction == "short" and exit_price <= pos.take_profit_1 * 1.01:
                                was_tp = True
                                exit_reason = "Take Profit triggered"

                        portfolio.close_position(symbol, exit_price, exit_reason)

                        # Record SL/TP for loss streak protection
                        if was_sl:
                            self._record_sl()
                        if was_tp:
                            self._record_tp()

                        # Auto-reverse position on SL if enabled
                        if was_sl and risk_config.auto_reverse_on_sl:
                            logger.info(f"🔄 Auto-reverse position on SL for {symbol}")
                            self._open_reverse_position(symbol, pos.direction, exit_price)

                        # Auto-reopen position on TP if enabled
                        if was_tp and risk_config.auto_reopen_on_tp:
                            logger.info(f"🔄 Auto-reopen position on TP for {symbol}")
                            self._open_same_direction_position(symbol, pos.direction, exit_price)
                self._current_positions[symbol] = None

    def _check_tp_sl_actions(self, symbol: str, position_info: dict):
        """Check for partial exit and trailing stop actions"""
        from config import strategy_config

        pos = portfolio.get_position(symbol)
        if not pos:
            return

        current_price = float(position_info.get("mark_price", 0) or position_info.get("last_price", 0))
        if not current_price:
            return

        entry_price = pos.entry_price
        sl_pct = strategy_config.sl_pct  # 1%
        tp_pct = strategy_config.tp_pct  # 2%
        partial_exit_tp_pct = strategy_config.partial_exit_tp_pct  # 1%
        trailing_activation_pct = strategy_config.trailing_stop_activation_pct  # 1.5%
        trailing_distance_pct = strategy_config.trailing_stop_distance_pct  # 0.5%

        # Calculate profit percentage
        if pos.direction == "long":
            profit_pct = (current_price - entry_price) / entry_price
        else:
            profit_pct = (entry_price - current_price) / entry_price

        # Check for partial exit at 1R (1% profit)
        if (strategy_config.partial_exit_enabled and
            not pos.partial_exit_done and
            profit_pct >= partial_exit_tp_pct):

            try:
                # Calculate partial exit size (50% of position)
                partial_size = pos.size * strategy_config.partial_exit_pct

                # Place partial exit order
                side = "Sell" if pos.direction == "long" else "Buy"
                result = self.api.place_order(
                    symbol=symbol,
                    side=side,
                    order_type="Market",
                    qty=partial_size
                )

                if result.get("retCode") == 0:
                    logger.info(f"✅ Partial exit executed: {partial_size} {symbol} at ${current_price:.2f} (profit: {profit_pct*100:.2f}%)")

                    # Update position tracking
                    pos.partial_exit_done = True
                    pos.partial_exit_size = partial_size
                    pos.size -= partial_size
                    pos.notional = pos.size * current_price
                else:
                    logger.warning(f"Partial exit failed: {result.get('retMsg')}")
            except Exception as e:
                logger.error(f"Error executing partial exit: {e}")

        # Check for trailing stop activation at 1.5R (1.5% profit)
        if (strategy_config.trailing_stop_enabled and
            not pos.trailing_stop_active and
            profit_pct >= trailing_activation_pct):

            try:
                # Calculate trailing stop price
                if pos.direction == "long":
                    trailing_stop_price = current_price * (1 - trailing_distance_pct)
                else:
                    trailing_stop_price = current_price * (1 + trailing_distance_pct)

                # Update stop loss on exchange
                side = "Buy" if pos.direction == "long" else "Sell"
                result = self.api.place_order(
                    symbol=symbol,
                    side=side,
                    order_type="StopMarket",
                    qty=pos.size,
                    stop_price=trailing_stop_price
                )

                if result.get("retCode") == 0:
                    logger.info(f"✅ Trailing stop activated: {symbol} at ${trailing_stop_price:.2f} (profit: {profit_pct*100:.2f}%)")

                    # Update position tracking
                    pos.trailing_stop_active = True
                    pos.trailing_stop_price = trailing_stop_price
                    pos.stop_loss = trailing_stop_price
                else:
                    logger.warning(f"Trailing stop activation failed: {result.get('retMsg')}")
            except Exception as e:
                logger.error(f"Error activating trailing stop: {e}")


    def _open_reverse_position(self, symbol: str, old_direction: str, current_price: float):
        """Open position in opposite direction after SL closure"""
        try:
            from config import trading_config, strategy_config

            # Check if reversal is allowed (smart reversal logic)
            if not self._should_reverse(symbol, old_direction):
                logger.info(f"Reversal not allowed for {symbol}, skipping")
                return

            # Check trading filters
            should_trade, trade_reason = self._should_trade(symbol)
            if not should_trade:
                logger.info(f"Trade blocked for {symbol}: {trade_reason}")
                return

            # Determine new direction (opposite of old)
            new_direction = "short" if old_direction == "long" else "long"
            new_side = "Sell" if new_direction == "short" else "Buy"

            logger.info(f"🔄 Opening reverse position: {symbol} {new_direction} at {current_price}")

            # Calculate position size using risk_manager
            position_size = risk_manager.calculate_position_size(
                account_balance=portfolio.get_account_balance(),
                entry_price=current_price,
                stop_loss_price=current_price * 0.98,  # 2% SL for position sizing
                atr=current_price * 0.01,
                signal_confidence=0.7,
                volatility_pct=1.0,
                symbol=symbol
            )
            qty = position_size.size

            # Calculate TP/SL from config (price-based)
            tp_pct = strategy_config.tp_pct  # 0.6%
            sl_pct = strategy_config.sl_pct  # 0.2%

            # Calculate price levels
            # For long: SL below entry, TP above entry
            # For short: SL above entry, TP below entry
            if new_direction == "long":
                sl = current_price * (1 - sl_pct)
                tp1 = current_price * (1 + tp_pct)
            else:  # short
                sl = current_price * (1 + sl_pct)
                tp1 = current_price * (1 - tp_pct)

            # Format qty and prices according to symbol requirements
            formatted_qty = self._format_qty(symbol, qty, is_market_order=True)
            sl = self._format_price(symbol, sl)
            tp1 = self._format_price(symbol, tp1)

            # Place order with adaptive qty retry
            result = self._place_order_with_adaptive_qty(
                symbol=symbol,
                side=new_side,
                order_type="Market",
                qty=formatted_qty,
                stop_loss=sl,
                take_profit=tp1
            )

            if result.get("retCode") == 0:
                logger.info(f"✅ Reverse position opened: {symbol} {new_direction} qty={qty}")
                self._last_trade_time = datetime.utcnow()  # Update last trade time
                # Update portfolio
                portfolio.open_position(
                    symbol=symbol,
                    direction=new_direction,
                    entry_price=current_price,
                    size=qty,
                    notional=qty * current_price,
                    leverage=self._instruments_info.get(symbol, {}).get("max_leverage", trading_config.default_leverage),
                    stop_loss=sl,
                    take_profit_1=tp1,
                    take_profit_2=tp1 * 1.5,
                    entry_reason=f"Auto-reverse after SL ({old_direction})",
                    regime="mad_mode",
                    rsi=50,
                    adx=20,
                    atr=current_price * 0.01
                )
            else:
                logger.error(f"❌ Failed to open reverse position: {result}")
        except Exception as e:
            logger.error(f"Error opening reverse position: {e}")

    def _open_same_direction_position(self, symbol: str, direction: str, current_price: float):
        """Open position in same direction after TP closure"""
        try:
            from config import trading_config, strategy_config

            # Check trading filters
            should_trade, trade_reason = self._should_trade(symbol)
            if not should_trade:
                logger.info(f"Trade blocked for {symbol}: {trade_reason}")
                return

            new_direction = direction  # Same direction
            new_side = "Sell" if new_direction == "short" else "Buy"

            logger.info(f"🔄 Reopening position: {symbol} {new_direction} at {current_price}")

            # Calculate position size using risk_manager
            position_size = risk_manager.calculate_position_size(
                account_balance=portfolio.get_account_balance(),
                entry_price=current_price,
                stop_loss_price=current_price * 0.98,  # 2% SL for position sizing
                atr=current_price * 0.01,
                signal_confidence=0.7,
                volatility_pct=1.0,
                symbol=symbol
            )
            qty = position_size.size

            # Calculate TP/SL from config (price-based)
            tp_pct = strategy_config.tp_pct  # 0.6%
            sl_pct = strategy_config.sl_pct  # 0.2%

            # Calculate price levels
            sl = current_price * (1 - sl_pct if new_direction == "long" else 1 + sl_pct)
            tp1 = current_price * (1 + tp_pct if new_direction == "long" else 1 - tp_pct)

            # Format qty and prices according to symbol requirements
            formatted_qty = self._format_qty(symbol, qty, is_market_order=True)
            sl = self._format_price(symbol, sl)
            tp1 = self._format_price(symbol, tp1)

            # Place order with adaptive qty retry
            result = self._place_order_with_adaptive_qty(
                symbol=symbol,
                side=new_side,
                order_type="Market",
                qty=formatted_qty,
                stop_loss=sl,
                take_profit=tp1
            )

            if result.get("retCode") == 0:
                logger.info(f"✅ Position reopened in same direction: {symbol} {new_direction} qty={qty}")
                self._last_trade_time = datetime.utcnow()  # Update last trade time
                # Update portfolio
                portfolio.open_position(
                    symbol=symbol,
                    direction=new_direction,
                    entry_price=current_price,
                    size=qty,
                    notional=qty * current_price,
                    leverage=self._instruments_info.get(symbol, {}).get("max_leverage", trading_config.default_leverage),
                    stop_loss=sl,
                    take_profit_1=tp1,
                    take_profit_2=tp1 * 1.5,
                    entry_reason=f"Auto-reopen after TP ({new_direction})",
                    regime="mad_mode",
                    rsi=50,
                    adx=20,
                    atr=current_price * 0.01
                )
            else:
                logger.error(f"❌ Failed to reopen position: {result}")
        except Exception as e:
            logger.error(f"Error reopening position: {e}")

    def _open_ema_first_position(self):
        """Open EMA-based first position for first symbol"""
        try:
            from config import trading_config, strategy_config
            from indicators import calculate_all_indicators

            # Use first symbol
            symbol = self.symbols[0]

            # Check trading filters
            should_trade, trade_reason = self._should_trade(symbol)
            if not should_trade:
                logger.info(f"Trade blocked for {symbol}: {trade_reason}")
                return

            df = self.market_data.get_dataframe(symbol, self.interval, limit=200)
            current_price = df['close'].iloc[-1]

            # Calculate EMAs
            ind = calculate_all_indicators(
                df,
                ema_fast=strategy_config.ema_fast_period,
                ema_medium=strategy_config.ema_medium_period,
                ema_slow=strategy_config.ema_slow_period,
                rsi_period=strategy_config.rsi_period,
                atr_period=strategy_config.atr_period
            )

            # Determine direction based on EMA crossover
            if ind.ema_9 > ind.ema_21:
                direction = "long"
                side = "Buy"
                reason = "EMA9 > EMA21 (bullish crossover)"
            elif ind.ema_9 < ind.ema_21:
                direction = "short"
                side = "Sell"
                reason = "EMA9 < EMA21 (bearish crossover)"
            else:
                # If equal, default to long
                direction = "long"
                side = "Buy"
                reason = "EMA9 = EMA21 (default to long)"

            logger.info(f"🎲 Opening EMA-based first position: {symbol} {direction} at {current_price} ({reason})")

            # Calculate position size using risk_manager
            position_size = risk_manager.calculate_position_size(
                account_balance=portfolio.get_account_balance(),
                entry_price=current_price,
                stop_loss_price=current_price * 0.96,  # 4% SL
                atr=current_price * 0.01,
                signal_confidence=0.7,
                volatility_pct=1.0,
                symbol=symbol
            )
            qty = position_size.size

            # Calculate TP/SL from config (price-based)
            tp_pct = strategy_config.tp_pct  # 0.6%
            sl_pct = strategy_config.sl_pct  # 0.2%

            # Calculate price levels
            sl = current_price * (1 - sl_pct if direction == "long" else 1 + sl_pct)
            tp1 = current_price * (1 + tp_pct if direction == "long" else 1 - tp_pct)

            # Format qty and prices according to symbol requirements
            formatted_qty = self._format_qty(symbol, qty, is_market_order=True)
            sl = self._format_price(symbol, sl)
            tp1 = self._format_price(symbol, tp1)

            # Place order with adaptive qty retry
            result = self._place_order_with_adaptive_qty(
                symbol=symbol,
                side=side,
                order_type="Market",
                qty=formatted_qty,
                stop_loss=sl,
                take_profit=tp1,
                market_unit="quoteCoin"
            )

            if result.get("retCode") == 0:
                logger.info(f"✅ EMA position opened: {symbol} {direction} qty={qty}")
                self._last_trade_time = datetime.utcnow()  # Update last trade time
                # Update portfolio
                portfolio.open_position(
                    symbol=symbol,
                    direction=direction,
                    entry_price=current_price,
                    size=qty,
                    notional=qty * current_price,
                    leverage=self._instruments_info.get(symbol, {}).get("max_leverage", trading_config.default_leverage),
                    stop_loss=sl,
                    take_profit_1=tp1,
                    take_profit_2=tp1 * 1.5,
                    entry_reason=f"EMA first position ({direction}) - {reason}",
                    regime="mad_mode",
                    rsi=ind.rsi if hasattr(ind, 'rsi') else 50,
                    adx=ind.adx if hasattr(ind, 'adx') else 20,
                    atr=current_price * 0.01
                )
                self._current_positions[symbol] = direction
            else:
                logger.error(f"❌ Failed to open EMA first position: {result}")
        except Exception as e:
            logger.error(f"Error opening EMA first position: {e}")

    def _open_ema_positions_for_symbols(self, symbols_to_open: list):
        """Open EMA-based positions for specific symbols"""
        from config import trading_config, strategy_config
        from indicators import calculate_all_indicators

        for symbol in symbols_to_open:
            try:
                # Check trading filters
                should_trade, trade_reason = self._should_trade(symbol)
                if not should_trade:
                    logger.info(f"Trade blocked for {symbol}: {trade_reason}")
                    continue

                df = self.market_data.get_dataframe(symbol, self.interval, limit=200)
                current_price = df['close'].iloc[-1]

                # Calculate EMAs
                ind = calculate_all_indicators(
                    df,
                    ema_fast=strategy_config.ema_fast_period,
                    ema_medium=strategy_config.ema_medium_period,
                    ema_slow=strategy_config.ema_slow_period,
                    rsi_period=strategy_config.rsi_period,
                    atr_period=strategy_config.atr_period
                )

                # Determine direction based on EMA crossover
                if ind.ema_9 > ind.ema_21:
                    direction = "long"
                    side = "Buy"
                    reason = "EMA9 > EMA21 (bullish crossover)"
                elif ind.ema_9 < ind.ema_21:
                    direction = "short"
                    side = "Sell"
                    reason = "EMA9 < EMA21 (bearish crossover)"
                else:
                    # If equal, default to long
                    direction = "long"
                    side = "Buy"
                    reason = "EMA9 = EMA21 (default to long)"

                logger.info(f"🎲 Opening EMA position for {symbol}: {direction} at {current_price} ({reason})")

                # Calculate position size using risk_manager
                position_size = risk_manager.calculate_position_size(
                    account_balance=portfolio.get_account_balance(),
                    entry_price=current_price,
                    stop_loss_price=current_price * 0.98,  # 2% SL (0.2% price with 50x leverage)
                    atr=current_price * 0.01,
                    signal_confidence=0.7,
                    volatility_pct=1.0,
                    symbol=symbol
                )
                qty = position_size.size

                # Calculate TP/SL from config (price-based)
                tp_pct = strategy_config.tp_pct  # 0.6%
                sl_pct = strategy_config.sl_pct  # 0.2%

                # Calculate price levels
                sl = current_price * (1 - sl_pct if direction == "long" else 1 + sl_pct)
                tp1 = current_price * (1 + tp_pct if direction == "long" else 1 - tp_pct)

                # Format qty and prices according to symbol requirements
                formatted_qty = self._format_qty(symbol, qty, is_market_order=True)
                sl = self._format_price(symbol, sl)
                tp1 = self._format_price(symbol, tp1)

                # Place order with adaptive qty retry
                result = self._place_order_with_adaptive_qty(
                    symbol=symbol,
                    side=side,
                    order_type="Market",
                    qty=formatted_qty,
                    stop_loss=sl,
                    take_profit=tp1
                )

                if result.get("retCode") == 0:
                    logger.info(f"✅ EMA position opened: {symbol} {direction} qty={qty}")
                    self._last_trade_time = datetime.utcnow()  # Update last trade time
                    # Update portfolio
                    portfolio.open_position(
                        symbol=symbol,
                        direction=direction,
                        entry_price=current_price,
                        size=qty,
                        notional=qty * current_price,
                        leverage=self._instruments_info.get(symbol, {}).get("max_leverage", trading_config.default_leverage),
                        stop_loss=sl,
                        take_profit_1=tp1,
                        take_profit_2=tp1 * 1.5,
                        entry_reason=f"EMA startup position ({direction}) - {reason}",
                        regime="mad_mode",
                        rsi=ind.rsi if hasattr(ind, 'rsi') else 50,
                        adx=ind.adx if hasattr(ind, 'adx') else 20,
                        atr=current_price * 0.01
                    )
                    self._current_positions[symbol] = direction
                else:
                    logger.error(f"❌ Failed to open EMA position for {symbol}: {result}")
            except Exception as e:
                logger.error(f"Error opening EMA position for {symbol}: {e}")

    def _fetch_and_analyze(self):
        """Fetch data and run analysis for current symbol"""
        # Cycle through symbols
        current_symbol = self.symbols[self._current_symbol_index]
        logger.info(f"🔄 Проверяю {current_symbol} ({self._current_symbol_index + 1}/{len(self.symbols)})")

        try:
            # Get fresh data for current symbol
            df = self.market_data.get_dataframe(current_symbol, self.interval, limit=200)

            if len(df) < 50:
                logger.warning(f"Недостаточно данных для {current_symbol}: {len(df)} свечей")
                return None
            
            current_price = df['close'].iloc[-1]

            # Update portfolio PnL for current symbol
            portfolio.update_positions({current_symbol: current_price})
            
            # Regime detection
            regime_analysis = regime_detector.analyze(df)

            # Generate signal for current symbol
            current_position = self._current_positions[current_symbol]
            signal = strategy.generate_signal(df, current_position, regime_analysis)
            
            return {
                "df": df,
                "price": current_price,
                "regime": regime_analysis,
                "signal": signal
            }
            
        except Exception as e:
            logger.error(f"Error in analysis: {e}", exc_info=True)
            return None
    
    def _process_signal(self, signal, analysis):
        """Process trading signal for current symbol"""
        current_symbol = self.symbols[self._current_symbol_index]
        current_position = self._current_positions[current_symbol]

        logger.info(f"🧠 Анализирую сигнал для {current_symbol}: {signal.signal_type.value} - {signal.reason}")

        if signal.signal_type == SignalType.HOLD:
            if current_position:
                pos = portfolio.get_position(current_symbol)
                if pos:
                    logger.info(f"⏸ Жду | {current_symbol} | Позиция: {current_position.upper()} | "
                              f"Прибыль: ${pos.current_pnl_net:.2f}")
            else:
                logger.info(f"⏸ Жду | {current_symbol} | Нет позиции")
            return

        # Handle entry signals
        if signal.is_entry:
            logger.info(f"📊 Сигнал на вход | {current_symbol} | {signal.signal_type.value} | Цена: ${signal.price:.2f}")
            self._handle_entry(signal, analysis, current_symbol)

        # NO MANUAL EXIT - positions only close by TP/SL from API
        # Manual exit signals are ignored
    
    def _handle_entry(self, signal, analysis, current_symbol):
        """Handle entry signal for specific symbol"""
        current_position = self._current_positions[current_symbol]
        if current_position:
            logger.warning(f"⚠️ Уже есть позиция {current_position} для {current_symbol}")
            return
        
        # Check risk limits
        balance = portfolio.get_account_balance()
        logger.info(f"💰 Баланс: ${balance:.2f}")
        can_trade, reason = risk_manager.can_trade(balance)
        
        if not can_trade:
            logger.warning(f"🛑 Вход запрещён: {reason}")
            return
        
        logger.info(f"✅ Риски в норме")

        # Calculate position size
        direction = "long" if signal.signal_type == SignalType.LONG_ENTRY else "short"
        logger.info(f"📐 Направление: {direction}")

        # Use absolute TP/SL from strategy
        sl = signal.stop_loss
        tp1 = signal.take_profit_1
        tp2 = signal.take_profit_2

        logger.info(f"🎯 Стоп: ${sl:.2f} | Тейк1: ${tp1:.2f} | Тейк2: ${tp2:.2f}")

        # Get indicators for volatility
        ind = analysis["regime"].details
        atr = ind.get("atr", signal.price * 0.01)
        logger.info(f"📊 Волатильность: ATR ${atr:.2f} | RSI {ind.get('rsi', 0):.1f} | ADX {ind.get('adx', 0):.1f}")

        position_size = risk_manager.calculate_position_size(
            account_balance=balance,
            entry_price=signal.price,
            stop_loss_price=sl,
            atr=atr,
            signal_confidence=signal.confidence,
            volatility_pct=ind.get("volatility", 1.0),
            symbol=current_symbol
        )

        logger.info(f"📦 Размер: {position_size.size:.4f} | Плечо: {position_size.leverage}x | Сумма: ${position_size.notional:.2f}")

        # Execute entry directly via API
        side = "Buy" if direction == "long" else "Sell"
        qty = position_size.size  # Already formatted by risk_manager

        filled_price = signal.price  # Fallback

        logger.info(f"🚀 Открываю позицию | {current_symbol} | {side} | {qty} | Рыночный ордер")

        # Retry logic with reduced position size and leverage
        success = False
        retry_count = 0
        max_retries = 10
        min_notional = 10.0  # Minimum $10 notional for Bybit
        current_leverage = self._instruments_info.get(current_symbol, {}).get("max_leverage", position_size.leverage)

        while not success and retry_count < max_retries:
            try:
                # Check minimum notional
                notional = qty * signal.price
                if notional < min_notional:
                    logger.warning(f"🛑 Размер позиции слишком мал: ${notional:.2f} < ${min_notional}")
                    break

                # Format qty according to symbol requirements
                formatted_qty = self._format_qty(current_symbol, qty, is_market_order=True)

                # Use MARKET order for immediate execution with absolute prices
                sl = self._format_price(current_symbol, sl)
                tp1 = self._format_price(current_symbol, tp1)
                result = self._place_order_with_adaptive_qty(
                    symbol=current_symbol,
                    side=side,
                    order_type="Market",
                    qty=formatted_qty,
                    stop_loss=sl,
                    take_profit=tp1
                )
                filled_price = signal.price
                success = True
                logger.info(f"✅ MARKET order filled at ${filled_price:.2f}")

                # Try to get actual filled price from response
                if result and "result" in result:
                    order_id = result["result"].get("orderId", "")
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Entry failed (attempt {retry_count + 1}/{max_retries}): {e}")

                # Reduce position size by 50% and retry
                qty = qty * 0.5
                qty = format_quantity(current_symbol, qty)
                retry_count += 1

                # Reduce leverage after 3 failed attempts
                if retry_count >= 3 and current_leverage > 10:
                    current_leverage = max(10, current_leverage - 10)
                    logger.info(f"📉 Снижаю плечо до {current_leverage}x")
                    # Keep original fixed TP/SL percentages (10.11% profit, 4.11% loss)
                    # Don't override with hardcoded values

                if retry_count < max_retries:
                    logger.info(f"🔄 Пробую с меньшим размером: {qty} (попытка {retry_count}/{max_retries}, плечо: {current_leverage}x)")
                else:
                    success = False
        
        if success:
            # Record in portfolio with absolute prices from signal
            portfolio.open_position(
                symbol=current_symbol,
                direction=direction,
                entry_price=filled_price,
                size=qty,
                notional=qty * filled_price,
                leverage=self._instruments_info.get(current_symbol, {}).get("max_leverage", position_size.leverage),
                stop_loss=sl,
                take_profit_1=tp1,
                take_profit_2=tp2,
                entry_reason=signal.reason,
                regime=signal.regime,
                rsi=ind.get("rsi", 0),
                adx=ind.get("adx", 0),
                atr=atr
            )

            self._current_positions[current_symbol] = direction

            logger.info(f"✅ Позиция открыта | {current_symbol} | {direction.upper()} | "
                       f"Цена: ${filled_price:.2f} | "
                       f"Количество: {qty:.4f} | "
                       f"Плечо: {position_size.leverage}x")
        else:
            logger.error("❌ Ошибка открытия позиции")

    def _handle_exit(self, signal, analysis, current_symbol):
        """Handle exit signal for specific symbol - DISABLED"""
        # MANUAL EXIT DISABLED - positions only close by TP/SL from API
        logger.info(f"⚠️ Ручной выход отключен | {current_symbol} | Жду TP/SL")
        return

    def _run_cycle(self):
        """Single trading cycle - only sync positions for TP/SL logic (no strategy signals)"""
        now = datetime.utcnow()

        # Skip if ran recently
        if self._last_check_time:
            elapsed = (now - self._last_check_time).total_seconds()
            if elapsed < self._check_interval_seconds:
                return

        self._last_check_time = now

        # Cycle to next symbol
        self._current_symbol_index = (self._current_symbol_index + 1) % len(self.symbols)
        current_symbol = self.symbols[self._current_symbol_index]

        try:
            # Sync state for all symbols to detect closed positions and trigger TP/SL logic
            self._sync_positions()

            # NO STRATEGY SIGNALS - only TP/SL logic is used
            # The bot only opens positions based on previous trade closure (SL → reverse, TP → same)

            # Update portfolio PnL for current symbol
            df = self.market_data.get_dataframe(current_symbol, self.interval, limit=200)
            if len(df) >= 50:
                current_price = df['close'].iloc[-1]
                portfolio.update_positions({current_symbol: current_price})

            # Log status periodically
            self._log_status_simple(current_symbol, current_price if len(df) >= 50 else 0)

        except Exception as e:
            logger.error(f"Error in cycle for {current_symbol}: {e}", exc_info=True)

    def _log_status_simple(self, current_symbol, current_price):
        """Log simplified status (no strategy signals)"""
        current_position = self._current_positions[current_symbol]

        if current_position:
            pos = portfolio.get_position(current_symbol)
            if pos:
                logger.info(f"📊 Статус | {current_symbol} | Цена: ${current_price:.2f} | "
                           f"Позиция: {current_position.upper()} | "
                           f"PnL: ${pos.current_pnl_net:.2f}")
            else:
                logger.info(f"📊 Статус | {current_symbol} | Цена: ${current_price:.2f} | "
                           f"Позиция: {current_position.upper()}")
        else:
            logger.info(f"📊 Статус | {current_symbol} | Цена: ${current_price:.2f} | Нет позиции")

    def _log_status(self, analysis):
        """Log current status"""
        current_symbol = self.symbols[self._current_symbol_index]
        current_position = self._current_positions[current_symbol]
        regime = analysis["regime"]
        signal = analysis["signal"]
        price = analysis["price"]

        risk_status = risk_manager.get_status(portfolio.get_account_balance())

        logger.info(f"📊 Статус | {current_symbol} | Цена: ${price:.2f} | "
                   f"Режим: {regime.regime.value} (ADX: {regime.adx:.1f}) | "
                   f"Сигнал: {signal.signal_type.value} | "
                   f"Позиция: {current_position or 'нет'} | "
                   f"Прибыль за день: ${risk_status.daily_pnl:.2f}")
    
    def run(self):
        """Main event loop with error handling for stability"""
        self.initialize()

        self._running = True
        logger.info("Starting main loop...")

        while self._running:
            try:
                if self._paused:
                    logger.info("⏸ Бот на паузе")
                    time.sleep(5)
                    continue

                # Config reload disabled - only reload when user clicks Apply button in web interface
                # now = datetime.utcnow()
                # if self._last_config_reload is None or (now - self._last_config_reload).total_seconds() >= self._config_reload_interval:
                #     self.reload_config()
                #     self._last_config_reload = now

                self._run_cycle()
                time.sleep(5)  # Check every 5 seconds

            except KeyboardInterrupt:
                logger.info("Shutdown requested")
                self._running = False
            except Exception as e:
                logger.error(f"Error in main loop (continuing): {e}", exc_info=True)
                time.sleep(10)  # Wait 10 seconds before retrying
                continue

        self.shutdown()

    def shutdown(self):
        """Graceful shutdown"""
        self._running = False
        logger.info("Shutting down...")
        logger.info("Bot stopped")
    
    def reload_config(self):
        """Reload config from web API"""
        try:
            import requests

            response = requests.get('http://127.0.0.1:5000/api/config', timeout=5)
            if response.status_code == 200:
                data = response.json()

                # Update trading config
                if 'trading' in data:
                    trading_config.update_from_dict(data['trading'])

                # Update strategy config
                if 'strategy' in data:
                    strategy_config.update_from_dict(data['strategy'])

                # Update risk config
                if 'risk' in data:
                    from config import risk_config
                    risk_config.update_from_dict(data['risk'])

                logger.info("✅ Config reloaded from API")
        except Exception as e:
            logger.warning(f"Failed to reload config: {e}")

    def stop(self):
        """Request stop"""
        self._running = False


def main():
    """Entry point - run infinite loop for Yandex Cloud"""
    bot = TradingBot()

    # Start web server in separate thread
    from web_server import set_bot_instance, run_web_server
    set_bot_instance(bot)
    import threading
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logger.info("Web dashboard started at http://127.0.0.1:5000")

    try:
        bot.run()
    except Exception as e:
        logger.error(f"Bot crashed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBot stopped by user")
