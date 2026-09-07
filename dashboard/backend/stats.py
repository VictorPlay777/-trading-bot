from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd


def _frame(trades):
    frame = pd.DataFrame(trades)
    if frame.empty:
        return frame
    for column in ("pnl", "fees_actual", "fees_est", "r_multiple", "duration_sec", "closed_ts", "qty"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["pnl"] = frame.get("pnl", 0).fillna(0.0)
    return frame


def _drawdown(frame):
    if frame.empty:
        return 0.0
    values = frame.sort_values("closed_ts")["pnl"].cumsum()
    peaks = values.cummax()
    drawdowns = peaks - values
    return float(drawdowns.max() or 0.0)


def compute_metrics(trades: list[dict]) -> dict:
    frame = _frame(trades)
    if frame.empty:
        return {
            "total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "profit_factor": None, "expectancy": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            "avg_r": None, "max_drawdown": 0.0, "max_drawdown_usd": 0.0,
            "max_drawdown_pct": None, "sharpe": None, "sharpe_note": "fewer than 20 trading days",
            "long_win_rate": 0.0, "short_win_rate": 0.0, "total_pnl": 0.0,
            "total_fees": 0.0, "fees_source": "fees_est", "gross_profit": 0.0,
            "gross_loss": 0.0, "best_trade": None, "worst_trade": None, "avg_duration_sec": 0.0,
        }
    wins = frame[frame.pnl > 0]
    losses = frame[frame.pnl <= 0]
    gross_profit = float(wins.pnl.sum())
    gross_loss = float(abs(losses.pnl.sum()))
    max_dd = _drawdown(frame)
    fee_actual = frame["fees_actual"] if "fees_actual" in frame else pd.Series(dtype=float)
    fees_source = "fees_actual" if not fee_actual.empty and fee_actual.notna().all() else "fees_est"
    fees = frame["fees_actual"] if fees_source == "fees_actual" else frame.get("fees_est", pd.Series(0, index=frame.index))
    dates = pd.to_datetime(frame.closed_ts, unit="s", utc=True, errors="coerce").dt.date
    daily = frame.assign(date=dates).groupby("date").pnl.sum()
    sharpe = None
    sharpe_note = None
    if len(daily) < 20:
        sharpe_note = "fewer than 20 trading days"
    elif float(daily.std(ddof=1) or 0) == 0:
        sharpe_note = "daily pnl standard deviation is zero"
    else:
        sharpe = float(daily.mean() / daily.std(ddof=1) * np.sqrt(365))
    def side_rate(side):
        subset = frame[frame.side == side]
        return float((subset.pnl > 0).mean() * 100) if len(subset) else 0.0
    return {
        "total_trades": int(len(frame)),
        "wins": int(len(wins)),
        "losses": int(len(losses)),
        "win_rate": float(len(wins) / len(frame) * 100),
        "profit_factor": (gross_profit / gross_loss) if gross_loss else None,
        "expectancy": float(frame.pnl.mean()),
        "avg_win": float(wins.pnl.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.pnl.mean()) if len(losses) else 0.0,
        "avg_r": float(frame.r_multiple.dropna().mean()) if "r_multiple" in frame and frame.r_multiple.notna().any() else None,
        "max_drawdown": max_dd,
        "max_drawdown_usd": max_dd,
        "max_drawdown_pct": None,
        "sharpe": sharpe,
        "sharpe_note": sharpe_note,
        "long_win_rate": side_rate("long"),
        "short_win_rate": side_rate("short"),
        "total_pnl": float(frame.pnl.sum()),
        "total_fees": float(fees.fillna(0).sum()),
        "fees_source": fees_source,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "best_trade": float(frame.pnl.max()),
        "worst_trade": float(frame.pnl.min()),
        "avg_duration_sec": float(frame.duration_sec.mean()) if "duration_sec" in frame else 0.0,
    }


def daily_pnl(trades):
    frame = _frame(trades)
    if frame.empty:
        return []
    frame["date"] = pd.to_datetime(frame.closed_ts, unit="s", utc=True, errors="coerce").dt.strftime("%Y-%m-%d")
    grouped = frame.groupby("date").agg(pnl=("pnl", "sum"), trades=("pnl", "size")).reset_index()
    return grouped.to_dict("records")


def cumulative_pnl(trades):
    frame = _frame(trades)
    if frame.empty:
        return []
    frame = frame.sort_values("closed_ts")
    return [
        {"ts": float(row.closed_ts), "cum_pnl": float(value)}
        for row, value in zip(frame.itertuples(), frame.pnl.cumsum())
    ]


def drawdown_series(cum):
    peak = 0.0
    output = []
    for row in cum:
        peak = max(peak, float(row["cum_pnl"]))
        output.append({"ts": row["ts"], "dd": peak - float(row["cum_pnl"])})
    return output


def by_strategy(trades):
    frame = _frame(trades)
    if frame.empty:
        return {}
    result = {}
    for strategy_id, group in frame.groupby(frame.strategy_id.fillna("unknown")):
        max_dd = _drawdown(group)
        wins = group[group.pnl > 0]
        losses = group[group.pnl <= 0]
        gross_loss = abs(float(losses.pnl.sum()))
        result[str(strategy_id)] = {
            "trades": int(len(group)),
            "win_rate": float(len(wins) / len(group) * 100),
            "pnl": float(group.pnl.sum()),
            "profit_factor": float(wins.pnl.sum() / gross_loss) if gross_loss else None,
            "max_drawdown": max_dd,
            "max_drawdown_pct": None,
            "avg_r": float(group.r_multiple.dropna().mean()) if "r_multiple" in group and group.r_multiple.notna().any() else None,
            "last_trade_ts": float(group.closed_ts.max()) if group.closed_ts.notna().any() else None,
        }
    return result


def period_bounds(period="all", start=None, end=None):
    now = datetime.now(timezone.utc)
    end_ts = now.timestamp()
    if period == "today":
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start_dt.timestamp(), end_ts
    if period in {"7d", "30d", "90d"}:
        return (now - timedelta(days=int(period[:-1]))).timestamp(), end_ts
    if period == "custom":
        return (float(start) if start is not None else None, float(end) if end is not None else end_ts)
    return None, None
