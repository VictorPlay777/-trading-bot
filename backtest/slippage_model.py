def simulate_slippage(notional: float, depth_usdt: float, spread_bps: float, latency_ms: int):
    depth_component = (notional / max(depth_usdt, 1.0)) * 0.0012
    spread_component = spread_bps / 10000.0 * 0.5
    latency_component = min(0.001, latency_ms / 1_000_000.0)
    return depth_component + spread_component + latency_component

