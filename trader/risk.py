import numpy as np

def position_size(equity: float, atr_value: float, sl_atr_mult: float, risk_per_trade: float) -> float:
    sl_dist = sl_atr_mult*atr_value
    if sl_dist<=0 or not np.isfinite(sl_dist): return 0.0
    risk_amount = equity*risk_per_trade
    return max(0.0, float(risk_amount/sl_dist))
