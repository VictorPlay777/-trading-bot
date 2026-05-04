class ExitEngine:
    def compute_brackets(self, side: str, entry: float, atr: float, sl_atr_mult: float, tp1_r: float, tp2_r: float):
        # Base unit is 1 ATR (floor at 0.1% of price to avoid zero-risk on flat markets).
        # sl_atr_mult, tp1_r, tp2_r are now ALL multipliers of ATR (not of each other).
        # This allows asymmetric TP vs SL (e.g. SL=3.5 ATR, TP=1.0 ATR for v3 clean mirror).
        # Backward compat: with sl_atr_mult=1.0 the formula produces identical results to v1.
        atr_unit = max(atr, entry * 0.001)
        sl_dist = sl_atr_mult * atr_unit
        if side == "long":
            sl = entry - sl_dist
            tp1 = entry + tp1_r * atr_unit
            tp2 = entry + tp2_r * atr_unit
        else:
            sl = entry + sl_dist
            tp1 = entry - tp1_r * atr_unit
            tp2 = entry - tp2_r * atr_unit
        # "risk" field preserved as SL distance for downstream sizing calculations.
        return {"sl": sl, "tp1": tp1, "tp2": tp2, "risk": sl_dist}

