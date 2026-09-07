from __future__ import annotations

from dashboard.backend.stats import by_strategy, compute_metrics, period_bounds


def test_metrics_and_strategy_breakdown():
    rows = [
        {"closed_ts": 1000 + index * 86400, "pnl": 10.0 if index % 2 == 0 else -5.0,
         "side": "long" if index % 2 == 0 else "short", "strategy_id": "s1",
         "r_multiple": 1.0 if index % 2 == 0 else -0.5, "fees_actual": 1.0,
         "duration_sec": 10}
        for index in range(30)
    ]
    metrics = compute_metrics(rows)
    assert metrics["total_trades"] == 30
    assert metrics["wins"] == 15
    assert metrics["win_rate"] == 0.5
    assert metrics["profit_factor"] == 2.0
    assert metrics["fees_source"] == "fees_actual"
    assert metrics["sharpe"] is not None
    assert by_strategy(rows)["s1"]["trades"] == 30


def test_period_bounds():
    assert period_bounds("all") == (None, None)
    start, end = period_bounds("custom", 1, 2)
    assert (start, end) == (1.0, 2.0)
