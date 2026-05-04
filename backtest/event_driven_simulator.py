from .slippage_model import simulate_slippage


class EventDrivenSimulator:
    def __init__(self, maker_fee=0.0002, taker_fee=0.0006):
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee

    def fill_pnl(self, side: str, entry: float, exit_px: float, notional: float, spread_bps: float, depth: float, latency_ms: int):
        raw = (exit_px - entry) / entry
        if side == "short":
            raw = -raw
        slip = simulate_slippage(notional, depth, spread_bps, latency_ms)
        net = raw - (2 * self.taker_fee) - slip
        return net * notional

