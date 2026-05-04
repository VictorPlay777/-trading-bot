from collections import defaultdict


def pnl_by_regime(trades):
    out = defaultdict(float)
    for t in trades:
        out[t.get("regime", "unknown")] += t.get("pnl", 0.0)
    return dict(out)

