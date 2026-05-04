import pandas as pd, numpy as np
def summarize(trades_df: pd.DataFrame, start_capital: float):
    if trades_df is None or trades_df.empty:
        return {'trades':0,'wins':0,'losses':0,'win_rate':None,'final_equity':start_capital,'net_profit':0.0,'avg_pnl':None,'max_drawdown':0.0}
    equity = start_capital
    curve = trades_df['equity_after'].tolist()
    wins = (trades_df['pnl']>0).sum(); losses=(trades_df['pnl']<=0).sum()
    max_dd = float((pd.Series(curve).cummax()-pd.Series(curve)).max()) if curve else 0.0
    return {'trades':int(len(trades_df)),'wins':int(wins),'losses':int(losses),'win_rate':float(wins/len(trades_df)),'final_equity':float(curve[-1]),'net_profit':float(curve[-1]-start_capital),'avg_pnl':float(trades_df['pnl'].mean()),'max_drawdown':max_dd}
