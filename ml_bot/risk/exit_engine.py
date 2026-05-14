class ExitEngine:
    def compute_brackets(self, side: str, entry: float, atr: float, sl_atr_mult: float, tp1_r: float, tp2_r: float,
                         position_notional: float = 0.0, percentage_based: bool = False, tp_sl_percentage: float = 0.01):
        # v8: Percentage-based TP/SL - calculate TP/SL as percentage of total position notional
        # instead of ATR multipliers. This ensures TP/SL scale with position size.
        if percentage_based and position_notional > 0:
            # Calculate target PnL as percentage of position notional
            target_pnl = position_notional * tp_sl_percentage
            # Calculate price move needed to achieve target PnL
            # price_move = target_pnl / (position_notional / entry) = target_pnl * entry / position_notional
            price_move = target_pnl * entry / position_notional
            # TP and SL are symmetric (equal distance from entry)
            if side == "long":
                sl = entry - price_move
                tp1 = entry + price_move
                tp2 = tp1  # Equal to tp1 for percentage-based mode
            else:
                sl = entry + price_move
                tp1 = entry - price_move
                tp2 = tp1  # Equal to tp1 for percentage-based mode
            sl_dist = price_move
        else:
            # Original ATR-based calculation
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

