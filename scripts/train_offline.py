import argparse, os, yaml, pandas as pd
from ml.features import add_features, FEATURES
from ml.labeler import label_regimes
from ml.model import ProbModel

import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--config', required=True); ap.add_argument('--csv', required=True)
    ap.add_argument('--symbol', required=True); ap.add_argument('--timeframe', required=True)
    args=ap.parse_args()
    cfg=yaml.safe_load(open(args.config,'r',encoding='utf-8'))
    models_dir=cfg['paths']['models_dir']; os.makedirs(models_dir, exist_ok=True)
    model_path=os.path.join(models_dir, f"model_{args.symbol}_{args.timeframe}.joblib")
    df=pd.read_csv(args.csv); 
    if 'time' in df.columns: df['time']=pd.to_datetime(df['time']); df=df.set_index('time')
    df=df[['open','high','low','close','volume']]
    df=add_features(df); df=label_regimes(df, horizon_bars=cfg['horizon_bars'], atr_mult=0.5)
    df_feat=df.dropna(subset=FEATURES+['y']).copy()
    X=df_feat[FEATURES].values; y=df_feat['y'].values
    m=ProbModel(); m.fit_partial(X,y); m.save(model_path); print('Модель сохранена:', model_path)
if __name__=='__main__': main()
