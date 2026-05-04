import numpy as np, pandas as pd
from ml.features import FEATURES, add_features
from ml.labeler import label_regimes
from ml.model import ProbModel

def run_backtest(ohlcv: pd.DataFrame, *, prob_threshold: float=0.62, tp_atr_mult: float=1.6, sl_atr_mult: float=1.0, horizon_bars: int=6, start_capital: float=1000.0, risk_per_trade: float=0.01, maker_fee: float=0.0002, taker_fee: float=0.0006, max_bars_open: int=None):
    if max_bars_open is None: max_bars_open = horizon_bars*3
    df = add_features(ohlcv.copy())
    df = label_regimes(df, horizon_bars=horizon_bars, atr_mult=0.5)
    df_feat = df.dropna(subset=FEATURES+['y']).copy()
    if df_feat.empty: return {}, pd.DataFrame(), pd.DataFrame()
    model = ProbModel(); equity=start_capital; equity_curve=[]; trades=[]
    start_idx = int(len(df_feat)*0.2)
    for i in range(start_idx, len(df_feat)-max_bars_open-1):
        X_train = df_feat[FEATURES].iloc[:i].values; y_train = df_feat['y'].iloc[:i].values
        if len(X_train)<50: continue
        model.fit_partial(X_train, y_train)
        x = df_feat[FEATURES].iloc[i].values; proba = model.predict_proba_row(x)
        p_up = proba.get(1,0.0); p_dn = proba.get(-1,0.0)
        equity_curve.append({'time': df_feat.index[i], 'equity': equity})
        signal=None
        if p_up>=prob_threshold: signal='long'
        elif p_dn>=prob_threshold: signal='short'
        if not signal: continue
        atr_val = df_feat['atr_14'].iloc[i]
        if atr_val<=0 or np.isnan(atr_val): continue
        entry_price = df_feat['close'].iloc[i]
        sl_dist = sl_atr_mult*atr_val; tp_dist=tp_atr_mult*atr_val
        risk_amount = equity*risk_per_trade; qty = risk_amount/sl_dist
        if qty<=0 or not np.isfinite(qty): continue
        fee_in = entry_price*qty*taker_fee
        outcome='timeout'; exit_price=entry_price; entry_time=df_feat.index[i]
        for j in range(1, max_bars_open+1):
            hi=df_feat['high'].iloc[i+j]; lo=df_feat['low'].iloc[i+j]
            if signal=='long':
                if hi>=entry_price+tp_dist: outcome='tp'; exit_price=entry_price+tp_dist; exit_time=df_feat.index[i+j]; break
                if lo<=entry_price-sl_dist: outcome='sl'; exit_price=entry_price-sl_dist; exit_time=df_feat.index[i+j]; break
            else:
                if lo<=entry_price-tp_dist: outcome='tp'; exit_price=entry_price-tp_dist; exit_time=df_feat.index[i+j]; break
                if hi>=entry_price+sl_dist: outcome='sl'; exit_price=entry_price+sl_dist; exit_time=df_feat.index[i+j]; break
        else:
            exit_time=df_feat.index[i+max_bars_open]
        fee_out = exit_price*qty*taker_fee
        pnl = (exit_price-entry_price)*qty if signal=='long' else (entry_price-exit_price)*qty
        pnl -= (fee_in + fee_out)
        equity += pnl
        trades.append({'entry_time':entry_time,'exit_time':exit_time,'signal':signal,'entry_price':float(entry_price),'exit_price':float(exit_price),'qty':float(qty),'outcome':outcome,'pnl':float(pnl),'fee_paid':float(fee_in+fee_out),'equity_after':float(equity)})
        equity_curve.append({'time': exit_time, 'equity': equity})
    curve = pd.DataFrame(equity_curve).drop_duplicates(subset=['time']).set_index('time').sort_index()
    trades_df = pd.DataFrame(trades)
    summary = {'trades':int(len(trades_df)),'final_equity':float(equity),'net_profit':float(equity-start_capital)}
    return summary, curve, trades_df
