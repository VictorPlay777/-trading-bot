import time, argparse, yaml, pandas as pd
from trader.exchange import Exchange
from ml.features import add_features, FEATURES
from ml.labeler import label_regimes
from ml.model import ProbModel
from trader.risk import position_size
from storage.db import make_session, Trade, Equity
from trader.state import save_kv, load_kv
from utils.logging import setup_logging

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config', required=True); ap.add_argument('--resume', action='store_true'); args=ap.parse_args()
    cfg=yaml.safe_load(open(args.config,'r',encoding='utf-8')); logger=setup_logging(cfg['paths']['logs_dir'])
    Session=make_session(cfg['paths']['db_url']); session=Session()
    ex=Exchange(cfg); model=ProbModel()
    import os
    model_path=f"{cfg['paths']['models_dir']}/model_{cfg['symbol']}_{cfg['timeframe']}.joblib"
    if os.path.exists(model_path): model.load(model_path); logger.info(f'Загружена модель: {model_path}')
    equity=cfg['start_capital']; state=load_kv(session,'paper_state') or {}
    if args.resume and 'equity' in state: equity=float(state['equity']); logger.info(f'Восстановлен equity={equity}')
    while True:
        ohlcv=ex.fetch_ohlcv(limit=600)
        df=pd.DataFrame(ohlcv, columns=['time','open','high','low','close','volume'])
        df['time']=pd.to_datetime(df['time'], unit='ms'); df=df.set_index('time')
        df=add_features(df); df=label_regimes(df, horizon_bars=cfg['horizon_bars'], atr_mult=0.5)
        df_feat=df.dropna(subset=FEATURES+['y'])
        if len(df_feat)<100: time.sleep(5); continue
        model.fit_partial(df_feat[FEATURES].values, df_feat['y'].values)
        row=df_feat.iloc[-1]; proba=model.predict_proba_row(row[FEATURES].values)
        p_up=proba.get(1,0.0); p_dn=proba.get(-1,0.0); signal=None
        if p_up>=cfg['prob_threshold']: signal='long'
        elif p_dn>=cfg['prob_threshold']: signal='short'
        if signal:
            atr_val=float(row['atr_14']); qty=position_size(equity, atr_val, cfg['sl_atr_mult'], cfg['risk_per_trade'])
            if qty<=0: time.sleep(5); continue
            entry_price=float(row['close']); sl_dist=cfg['sl_atr_mult']*atr_val; tp_dist=cfg['tp_atr_mult']*atr_val
            taker_fee=cfg['taker_fee']; fee_in=entry_price*qty*taker_fee
            max_bars=cfg['horizon_bars']*3; outcome='timeout'; exit_price=entry_price
            sub=df_feat.iloc[-max_bars-1:]
            for i in range(1, len(sub)):
                hi=sub['high'].iloc[i]; lo=sub['low'].iloc[i]
                if signal=='long':
                    if hi>=entry_price+tp_dist: outcome='tp'; exit_price=entry_price+tp_dist; break
                    if lo<=entry_price-sl_dist: outcome='sl'; exit_price=entry_price-sl_dist; break
                else:
                    if lo<=entry_price-tp_dist: outcome='tp'; exit_price=entry_price-tp_dist; break
                    if hi>=entry_price+sl_dist: outcome='sl'; exit_price=entry_price+sl_dist; break
            fee_out=exit_price*qty*taker_fee
            pnl=(exit_price-entry_price)*qty if signal=='long' else (entry_price-exit_price)*qty
            pnl -= (fee_in+fee_out); equity += pnl
            t=Trade(symbol=cfg['symbol'], direction=signal, entry_time=row.name, exit_time=sub.index[i] if outcome!='timeout' else row.name, entry_price=entry_price, exit_price=float(exit_price), qty=float(qty), pnl=float(pnl), outcome=outcome, fee_paid=float(fee_in+fee_out))
            session.add(t); session.add(Equity(equity=float(equity))); session.commit()
            logger.info(f'PAPER {signal} pnl={pnl:.2f} equity={equity:.2f}')
            save_kv(session, 'paper_state', {'equity': equity})
        time.sleep(5)
if __name__=='__main__': main()
