class ExposureLimits:
    def __init__(self, max_concurrent: int, max_per_symbol: int = 1):
        self.max_concurrent = max_concurrent
        self.max_per_symbol = max_per_symbol

    def allow(self, open_positions: list, symbol: str):
        if len(open_positions) >= self.max_concurrent:
            return False
        sym_count = sum(1 for p in open_positions if p.get("symbol") == symbol and float(p.get("size", 0)) > 0)
        return sym_count < self.max_per_symbol

