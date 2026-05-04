class PositionSizer:
    def __init__(self, base_notional: float):
        self.base_notional = base_notional

    def multiplier(self, edge, volatility, trend_strength, liquidity):
        if edge < 0.03:
            base = 0.30
        elif edge < 0.10:
            base = 0.70
        elif edge < 0.18:
            base = 1.00
        else:
            base = 1.25
        vol_adj = max(0.6, min(1.2, 1.0 - volatility * 12.0))
        trend_adj = max(0.8, min(1.2, 1.0 + trend_strength * 10.0))
        liq_adj = max(0.5, min(1.2, liquidity))
        return max(0.2, min(1.5, base * vol_adj * trend_adj * liq_adj))

    def size_notional(self, edge, volatility, trend_strength, liquidity):
        return self.base_notional * self.multiplier(edge, volatility, trend_strength, liquidity)

