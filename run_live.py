import time, argparse, yaml, pandas as pd
from trader.exchange_demo import Exchange
from ml.features import add_features, FEATURES
from ml.labeler import label_regimes
from ml.model import ProbModel
from trader.risk import position_size
from trader.broker import Broker
from storage.db import make_session, Trade, Equity
from trader.state import save_kv, load_kv
from utils.logging import setup_logging

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config', required=True); ap.add_argument('--resume', action='store_true'); args=ap.parse_args()
    cfg=yaml.safe_load(open(args.config,'r',encoding='utf-8')); cfg['mode']='live'; logger=setup_logging(cfg['paths']['logs_dir'])
    Session=make_session(cfg['paths']['db_url']); session=Session()
    ex=Exchange(cfg); broker=Broker(ex, cfg, logger); model=ProbModel()
    # Set leverage to 1x at startup
    try:
        leverage = cfg.get('leverage', 1)
        ex.set_leverage(leverage)
        logger.info(f'Leverage set to {leverage}x')
    except Exception as e:
        logger.warning(f'Could not set leverage: {e}')
    import os
    model_path=f"{cfg['paths']['models_dir']}/model_{cfg['symbol']}_{cfg['timeframe']}.joblib"
    if os.path.exists(model_path): model.load(model_path); logger.info(f'Загружена модель: {model_path}')
    state=load_kv(session,'live_state') or {}
    
    # PnL thresholds for closing positions (percentage of position value)
    TP_PERCENT = 0.004  # 0.4% profit target for trailing TP
    SL_PERCENT = -0.004  # -0.4% stop loss
    BREAKEVEN_PERCENT = 0.004  # +0.4% to move SL to breakeven
    prev_unrealised_pnl = None  # Track previous PnL to check if it's growing
    breakeven_triggered = False  # Track if SL has been moved to breakeven
    last_candle_time = None  # Track last candle time to avoid retraining on same data
    
    while True:
        # Get real balance and positions from API
        balance_data=ex.get_wallet_balance()
        if balance_data.get('retCode')==0:
            accounts=balance_data.get('result',{}).get('list',[])
            if accounts:
                total_equity=float(accounts[0].get('totalEquity',0))
                logger.info(f'Real API equity: {total_equity:.2f} USDT')
        # Get positions
        positions_data=ex.get_positions(cfg['symbol'])
        current_position=None
        if positions_data.get('retCode')==0:
            positions=positions_data.get('result',{}).get('list',[])
            for pos in positions:
                if pos.get('symbol')==cfg['symbol'] and float(pos.get('size',0))>0:
                    current_position=pos
                    unrealised_pnl=float(pos.get('unrealisedPnl',0))
                    logger.info(f'Position: {pos.get("side")} size={pos.get("size")} unrealisedPnl={unrealised_pnl:.2f}')
                    
                    # Calculate TP and SL based on position value
                    position_value = float(pos.get('positionValue', 0))
                    tp_threshold = position_value * TP_PERCENT
                    sl_threshold = position_value * SL_PERCENT
                    breakeven_threshold = position_value * BREAKEVEN_PERCENT
                    logger.info(f'Position value: {position_value:.2f} USDT, TP: {tp_threshold:.2f} USDT, SL: {sl_threshold:.2f} USDT')
                    
                    # Check SL (before breakeven)
                    if not breakeven_triggered and unrealised_pnl <= sl_threshold:
                        logger.info(f'SL triggered: {unrealised_pnl:.2f} <= {sl_threshold:.2f}')
                        close_side = "Sell" if pos.get('side') == "Buy" else "Buy"
                        size = float(pos.get('size'))
                        order = ex.market_sell(size) if close_side == "Sell" else ex.market_buy(size)
                        logger.info(f'Closed position on SL with market order: {order}')
                        current_position = None
                        break
                    
                    # Check breakeven trigger
                    if not breakeven_triggered and unrealised_pnl >= breakeven_threshold:
                        breakeven_triggered = True
                        logger.info(f'Breakeven triggered: PnL reached {unrealised_pnl:.2f} >= {breakeven_threshold:.2f}')
                    
                    # Check TP with trailing
                    if unrealised_pnl >= tp_threshold:
                        # Check if PnL is still growing
                        if prev_unrealised_pnl is not None and unrealised_pnl < prev_unrealised_pnl:
                            logger.info(f'TP reached and PnL started falling: {prev_unrealised_pnl:.2f} -> {unrealised_pnl:.2f}')
                            close_side = "Sell" if pos.get('side') == "Buy" else "Buy"
                            size = float(pos.get('size'))
                            order = ex.market_sell(size) if close_side == "Sell" else ex.market_buy(size)
                            logger.info(f'Closed position on TP with market order: {order}')
                            current_position = None
                        else:
                            logger.info(f'TP reached but PnL still growing: {unrealised_pnl:.2f} (prev: {prev_unrealised_pnl})')
                    prev_unrealised_pnl = unrealised_pnl
                    break
        # Fetch OHLCV
        ohlcv=ex.fetch_ohlcv(limit=600)
        logger.info(f'Загружено {len(ohlcv)} свечей')
        # Save raw timestamp of latest candle for retrain check
        latest_candle_ts = ohlcv[-1][0] if ohlcv else None
        df=pd.DataFrame(ohlcv, columns=['time','open','high','low','close','volume'])
        df['time']=pd.to_datetime(df['time'], unit='s'); df=df.set_index('time')
        logger.info(f'DF после обработки: {len(df)} строк')
        df=add_features(df); logger.info(f'После add_features: {len(df)} строк')
        df=label_regimes(df, horizon_bars=cfg['horizon_bars'], atr_mult=0.5); logger.info(f'После label_regimes: {len(df)} строк')
        df_feat=df.dropna(subset=FEATURES+['y'])
        logger.info(f'Загружено {len(df_feat)} фичей (нужно 100)')
        if len(df_feat)<100: time.sleep(5); continue
        # Only retrain model when new candle appears (not every 5 seconds!)
        if last_candle_time is None or latest_candle_ts != last_candle_time:
            model.fit_partial(df_feat[FEATURES].values, df_feat['y'].values)
            last_candle_time = latest_candle_ts
            logger.info(f'Model retrained on new candle: {pd.to_datetime(latest_candle_ts, unit="s")}')
        row=df_feat.iloc[-1]; proba=model.predict_proba_row(row[FEATURES].values)
        p_up=proba.get(1,0.0); p_dn=proba.get(-1,0.0); signal=None
        logger.info(f'ML probs: p_up={p_up:.3f} p_dn={p_dn:.3f} threshold={cfg["prob_threshold"]}')
        if p_up>=cfg['prob_threshold']: signal='long'
        elif p_dn>=cfg['prob_threshold']: signal='short'
        # Only open new position if no current position
        if signal and not current_position:
            # Use fixed position size of 100K USDT for all bots
            position_value_usdt = 100000.0  # Fixed 100K USDT position size
            current_price=float(row['close'])
            qty = position_value_usdt / current_price
            if qty<=0: time.sleep(5); continue
            # Round qty based on price (different precision for different coins)
            if current_price > 3000:
                qty = round(qty, 3)  # BTC: 3 decimals (min 0.001)
            elif current_price > 100:
                qty = round(qty, 2)  # ETH: 2 decimals (min 0.01)
            elif current_price > 10:
                qty = round(qty, 1)  # SOL: 1 decimal (min 0.1)
            else:
                qty = int(qty)  # XRP, ADA: integer (min 1)
            # Use market order for guaranteed execution
            if signal=='long':
                order=ex.market_buy(qty)
            else:
                order=ex.market_sell(qty)
            logger.info(f'Opened {signal} market position qty={qty:.4f} value={position_value_usdt:.2f} USDT')
            # Reset tracking variables for new position
            prev_unrealised_pnl = None
            breakeven_triggered = False
        time.sleep(5)
if __name__=='__main__': main()
