import pandas as pd

def label_regimes(df: pd.DataFrame, horizon_bars: int, atr_mult: float=0.5)->pd.DataFrame:
    df=df.copy()
    df['fwd_close']=df['close'].shift(-horizon_bars)
    df['fwd_ret']=(df['fwd_close']-df['close'])/df['close']
    atr_pct=(df['atr_14']/df['close']).fillna(0)
    thresh=atr_mult*atr_pct
    df['y']=0
    df.loc[df['fwd_ret']>thresh,'y']=1
    df.loc[df['fwd_ret']<-thresh,'y']=-1
    return df
