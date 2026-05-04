class PortfolioHeat:
    def __init__(self, max_heat: float):
        self.max_heat = max_heat

    def can_open(self, used_notional: float, equity: float, new_notional: float):
        if equity <= 0:
            return False
        return ((used_notional + new_notional) / equity) <= self.max_heat

