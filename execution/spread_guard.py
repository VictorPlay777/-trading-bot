class SpreadGuard:
    def __init__(self, max_spread_bps: float):
        self.max_spread_bps = max_spread_bps

    def allow(self, spread_bps: float) -> bool:
        return spread_bps <= self.max_spread_bps

