class SlippageGuard:
    def estimate(self, spread_bps: float, depth_usdt: float, notional: float):
        if depth_usdt <= 0:
            return 0.01
        impact = (notional / depth_usdt) * 0.0015
        spread = spread_bps / 10000.0
        return max(0.0, spread * 0.5 + impact)

