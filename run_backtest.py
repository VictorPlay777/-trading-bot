import sys, os
if __package__ is None or __package__ == "":
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import os, argparse, yaml, pandas as pd
from backtester.backtest import run_backtest
from storage.db import make_session, Trade, Equity
from utils.logging import setup_logging
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config', required=True); ap.add_argument('--csv', required=True); args=ap.parse_args()
    cfg=yaml.safe_load(open(args.config,'r',encoding='utf-8')); logger=setup_logging(cfg['paths']['logs_dir'])
    Session=make_session(cfg['paths']['db_url']); session=Session()
    df=pd.read_csv(args.csv); 
    if 'time' in df.columns: df['time']=pd.to_datetime(df['time']); df=df.set_index('time')
    df=df[['open','high','low','close','volume']]
    summary, curve, trades=run_backtest(df, prob_threshold=cfg['prob_threshold'], tp_atr_mult=cfg['tp_atr_mult'], sl_atr_mult=cfg['sl_atr_mult'], horizon_bars=cfg['horizon_bars'], start_capital=cfg['start_capital'], risk_per_trade=cfg['risk_per_trade'], maker_fee=cfg['maker_fee'], taker_fee=cfg['taker_fee'])
    os.makedirs('storage', exist_ok=True)
    trades_path=f"storage/trades_{cfg['symbol']}_{cfg['timeframe']}.csv"; curve_path=f"storage/equity_{cfg['symbol']}_{cfg['timeframe']}.csv"
    trades.to_csv(trades_path, index=False); curve.to_csv(curve_path)
    for _,r in trades.iterrows(): session.add(Trade(symbol=cfg['symbol'], direction=r['signal'], entry_time=r['entry_time'], exit_time=r['exit_time'], entry_price=r['entry_price'], exit_price=r['exit_price'], qty=r['qty'], pnl=r['pnl'], outcome=r['outcome'], fee_paid=r['fee_paid']))
    session.commit(); 
    for idx,val in curve['equity'].items(): session.add(Equity(time=idx, equity=float(val)))
    session.commit()
    print('Summary:', summary); print('Saved:', trades_path, curve_path)
if __name__=='__main__': main()
