"""
TP/SL research module — isolated from trading logic.

This module only reads historical trade records and market data, then
virtually simulates fixed TP/SL brackets for every trade. It does NOT
place, modify, or close any orders.

Usage:
    python research/tp_sl_research.py --trades logs/trades.jsonl --output research/tp_sl_report

Outputs:
    research/tp_sl_report.json
    research/tp_sl_report.txt
    research/tp_sl_report_heatmap.html
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
import traceback
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
@dataclass
class ResearchConfig:
    """Tune the virtual TP/SL grid and report thresholds."""

    tp_values: List[float] = field(default_factory=lambda: [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0])
    sl_values: List[float] = field(default_factory=lambda: [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0])
    fee_rate: float = 0.0006  # taker fee per side (0.06%)
    timeframe: str = "1m"     # OHLCV granularity for simulation
    max_hold_hours: float = 48.0
    min_trades: int = 30
    low_data_trades: int = 100
    region_min_combo: int = 4  # minimum grid cells in a stable region
    region_min_neighbors: int = 2
    pf_good: float = 1.2
    n_walk_forward_folds: int = 3
    cache_dir: str = "data/research_ohlcv"
    output_dir: str = "research/tp_sl_output"
    default_pair: Optional[str] = None

    def save(self, path: Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, default=str)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ResearchConfig":
        allowed = {f.name for f in cls.__dataclass_fields__.values()}
        kwargs = {k: v for k, v in d.items() if k in allowed}
        return cls(**kwargs)


# ---------------------------------------------------------------------------
# Trade loading
# ---------------------------------------------------------------------------
@dataclass
class Trade:
    trade_id: str
    symbol: str
    side: str  # long or short
    entry_price: float
    qty: float
    notional: float
    opened_ts: float
    closed_ts: Optional[float]
    signal: Dict[str, Any]
    fee_rate: float
    source_schema: str = ""


def _to_float(x, default: float = 0.0) -> float:
    if x is None:
        return default
    try:
        return float(x)
    except Exception:
        return default


def _to_qty(record: Dict[str, Any]) -> float:
    for key in ("qty_total", "quantity", "qty", "amount"):
        v = record.get(key)
        if v is not None:
            try:
                return float(v)
            except Exception:
                continue
    return 0.0


def _infer_side(record: Dict[str, Any]) -> str:
    for key in ("side", "direction"):
        v = record.get(key)
        if v:
            v = str(v).lower()
            if v in ("long", "buy"):
                return "long"
            if v in ("short", "sell"):
                return "short"
    return "long"


def _infer_symbol(record: Dict[str, Any]) -> str:
    return str(record.get("symbol", record.get("pair", ""))).upper()


def _infer_fees(record: Dict[str, Any]) -> float:
    # If a total commission is given, translate to per-side rate for simulation.
    qty = _to_qty(record)
    entry = _to_float(record.get("entry_price"))
    if qty > 0 and entry > 0:
        notional = entry * qty
    else:
        notional = _to_float(record.get("notional_entry"), 1.0)
    commission = _to_float(record.get("commission"), 0.0)
    if commission > 0 and notional > 0:
        return commission / notional / 2.0
    return 0.0


def load_trades(trades_path: Path) -> List[Trade]:
    """Load closed trades from a JSONL file written by the bot."""
    if not trades_path.exists():
        raise FileNotFoundError(trades_path)

    trades: List[Trade] = []
    with open(trades_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue

            # Skip header / schema-only lines.
            if record.get("schema") in ("trade_v2", "selective_trade_v1") and not record.get("trade_id"):
                continue

            side = _infer_side(record)
            symbol = _infer_symbol(record)
            if not symbol:
                continue

            opened = _to_float(record.get("opened_ts", record.get("entry_timestamp")))
            closed = record.get("closed_ts", record.get("exit_timestamp"))
            closed = _to_float(closed) if closed is not None else None
            entry = _to_float(record.get("entry_price"))
            if entry <= 0 or opened <= 0:
                continue

            qty = _to_qty(record)
            notional = _to_float(record.get("notional_entry"))
            if notional <= 0 and qty > 0:
                notional = entry * qty
            if qty <= 0 and notional > 0:
                qty = notional / entry

            fee_rate = _infer_fees(record)

            # Prefer bot's own signal snapshot metadata for condition analysis.
            signal = record.get("signal", record.get("metadata", {})) or {}
            if isinstance(signal, str):
                try:
                    signal = json.loads(signal)
                except Exception:
                    signal = {}

            trades.append(
                Trade(
                    trade_id=str(record.get("trade_id", f"{symbol}_{opened}")),
                    symbol=symbol,
                    side=side,
                    entry_price=entry,
                    qty=qty,
                    notional=notional,
                    opened_ts=opened,
                    closed_ts=closed,
                    signal=signal,
                    fee_rate=fee_rate,
                    source_schema=record.get("schema", ""),
                )
            )
    return trades


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------
class OhlcvLoader:
    """Fetch and cache Bybit OHLCV for arbitrary symbol/time ranges."""

    def __init__(self, cache_dir: Path, timeframe: str = "1m"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeframe = timeframe
        self._exchange: Any = None

    def _exchange_init(self) -> Any:
        if self._exchange is None:
            import ccxt
            self._exchange = ccxt.bybit({
                "enableRateLimit": True,
                "options": {"defaultType": "linear"},
            })
        return self._exchange

    @staticmethod
    def _ccxt_symbol(symbol: str) -> str:
        """Convert bot symbol like BTCUSDT into ccxt unified linear name."""
        if "/" in symbol:
            return symbol
        s = symbol.upper()
        for quote in ("USDT", "USDC", "BTC", "ETH"):
            if s.endswith(quote):
                base = s[: -len(quote)]
                return f"{base}/{quote}:{quote}"
        return s

    @staticmethod
    def _tf_to_ms(tf: str) -> int:
        unit = tf[-1]
        num = int(tf[:-1])
        multipliers = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}
        return num * multipliers.get(unit, 60_000)

    def _cache_path(self, symbol: str, start_ms: int, end_ms: int) -> Path:
        key = f"{symbol}_{self.timeframe}_{start_ms}_{end_ms}"
        return self.cache_dir / f"{key}.csv"

    def load(self, symbol: str, start_s: float, end_s: float) -> pd.DataFrame:
        """Load OHLCV for [start_s, end_s] (unix seconds)."""
        start_ms = int(start_s * 1000)
        end_ms = int(end_s * 1000)
        cache = self._cache_path(symbol, start_ms, end_ms)
        if cache.exists():
            df = pd.read_csv(cache, parse_dates=["ts"])
            if not df.empty:
                df["ts_ms"] = df["ts"].astype(np.int64) // 1_000_000
                return df

        df = self._fetch(symbol, start_ms, end_ms)
        if not df.empty:
            df.to_csv(cache, index=False)
        return df

    def _fetch(self, symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
        exchange = self._exchange_init()
        ccxt_symbol = self._ccxt_symbol(symbol)
        interval_ms = self._tf_to_ms(self.timeframe)
        all_candles: List[List[float]] = []
        since = start_ms
        limit = 1000

        while since <= end_ms:
            try:
                candles = exchange.fetch_ohlcv(ccxt_symbol, self.timeframe, since=since, limit=limit)
            except Exception as e:
                print(f"[DATA] {symbol} fetch failed at {since}: {e}")
                break

            if not candles:
                break

            all_candles.extend(candles)
            last_ts = int(candles[-1][0])
            if last_ts >= end_ms:
                break
            next_since = last_ts + interval_ms
            if next_since <= since:
                break
            since = next_since

        if not all_candles:
            return pd.DataFrame()

        df = pd.DataFrame(all_candles, columns=["ts_ms", "open", "high", "low", "close", "volume"])
        df = df.drop_duplicates(subset=["ts_ms"]).sort_values("ts_ms").reset_index(drop=True)
        df["ts"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
        return df

    def load_for_trade(self, trade: Trade, hold_seconds: float) -> pd.DataFrame:
        end = (trade.closed_ts or (trade.opened_ts + hold_seconds)) + 300
        return self.load(trade.symbol, trade.opened_ts, end)


# ---------------------------------------------------------------------------
# Virtual TP/SL simulation
# ---------------------------------------------------------------------------
@dataclass
class SimResult:
    tp: float
    sl: float
    exit_type: str  # TP, SL, TIMEOUT
    exit_price: float
    pnl: float
    return_pct: float
    hold_seconds: float
    is_win: bool
    tp_hit: bool
    sl_hit: bool
    first_hit: str


def _resolve_both_hit(side: str, candle: pd.Series) -> str:
    """Intrabar tie-break when a candle touches both TP and SL."""
    if side == "long":
        return "TP" if candle["close"] >= candle["open"] else "SL"
    return "TP" if candle["close"] <= candle["open"] else "SL"


def simulate_trade(trade: Trade, candles: pd.DataFrame, tp_pct: float, sl_pct: float) -> SimResult:
    """Walk forward from trade.opened_ts and determine the first TP or SL hit."""
    if candles.empty:
        return SimResult(tp=tp_pct, sl=sl_pct, exit_type="TIMEOUT", exit_price=trade.entry_price,
                         pnl=0.0, return_pct=0.0, hold_seconds=0.0, is_win=False,
                         tp_hit=False, sl_hit=False, first_hit="")

    entry = trade.entry_price
    if trade.side == "long":
        tp_price = entry * (1 + tp_pct / 100)
        sl_price = entry * (1 - sl_pct / 100)
    else:
        tp_price = entry * (1 - tp_pct / 100)
        sl_price = entry * (1 + sl_pct / 100)

    # First candle that could contain the entry time.
    mask = candles["ts_ms"] >= (trade.opened_ts - 60) * 1000
    if mask.any():
        start_idx = mask.idxmax()
    else:
        start_idx = 0

    exit_type = "TIMEOUT"
    exit_price = float(candles.iloc[-1]["close"])
    hold_seconds = 0.0
    tp_hit = False
    sl_hit = False
    first_hit = ""

    for idx in range(start_idx, len(candles)):
        c = candles.iloc[idx]
        high, low = float(c["high"]), float(c["low"])

        if trade.side == "long":
            hit_tp = high >= tp_price
            hit_sl = low <= sl_price
        else:
            hit_tp = low <= tp_price
            hit_sl = high >= sl_price

        if hit_tp and hit_sl:
            first_hit = _resolve_both_hit(trade.side, c)
            exit_price = tp_price if first_hit == "TP" else sl_price
            exit_type = first_hit
            hold_seconds = (float(c["ts_ms"]) / 1000.0) - trade.opened_ts
            tp_hit = first_hit == "TP"
            sl_hit = first_hit == "SL"
            break

        if hit_tp:
            exit_price = tp_price
            exit_type = "TP"
            hold_seconds = (float(c["ts_ms"]) / 1000.0) - trade.opened_ts
            tp_hit = True
            break

        if hit_sl:
            exit_price = sl_price
            exit_type = "SL"
            hold_seconds = (float(c["ts_ms"]) / 1000.0) - trade.opened_ts
            sl_hit = True
            break

    # Gross percentage.
    if trade.side == "long":
        ret_pct = (exit_price - entry) / entry * 100
    else:
        ret_pct = (entry - exit_price) / entry * 100

    notional = max(trade.notional, entry * trade.qty)
    fee_pct = (trade.fee_rate or 0.0006) * 2 * 100
    pnl = notional * (ret_pct - fee_pct) / 100.0

    # If known real closed_ts, force timeout at last candle close if nothing hit.
    if exit_type == "TIMEOUT" and trade.closed_ts is not None:
        hold_seconds = max(0.0, trade.closed_ts - trade.opened_ts)

    return SimResult(
        tp=tp_pct,
        sl=sl_pct,
        exit_type=exit_type,
        exit_price=exit_price,
        pnl=pnl,
        return_pct=ret_pct - fee_pct,
        hold_seconds=hold_seconds,
        is_win=pnl > 0,
        tp_hit=tp_hit,
        sl_hit=sl_hit,
        first_hit=first_hit or exit_type,
    )


def compute_mfe_mae(trade: Trade, candles: pd.DataFrame) -> Tuple[float, float]:
    """Return MFE% and MAE% for this trade over the candle path."""
    if candles.empty:
        return 0.0, 0.0

    mask = candles["ts_ms"] >= (trade.opened_ts - 60) * 1000
    if mask.any():
        start_idx = mask.idxmax()
    else:
        start_idx = 0

    if start_idx >= len(candles):
        return 0.0, 0.0

    slice_df = candles.iloc[start_idx:]
    highs = slice_df["high"].astype(float).values
    lows = slice_df["low"].astype(float).values
    entry = trade.entry_price

    if trade.side == "long":
        mfe = max((highs - entry) / entry * 100)
        mae = max((entry - lows) / entry * 100)
    else:
        mfe = max((entry - lows) / entry * 100)
        mae = max((highs - entry) / entry * 100)

    return float(np.nan_to_num(mfe)), float(np.nan_to_num(mae))


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
@dataclass
class ComboStats:
    tp: float
    sl: float
    trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate: float
    loss_rate: float
    tp_hits: int
    sl_hits: int
    tp_hit_rate: float
    sl_hit_rate: float
    avg_pnl: float
    median_pnl: float
    total_pnl: float
    profit_factor: float
    expectancy: float
    avg_win: float
    avg_loss: float
    max_win_streak: int
    max_loss_streak: int
    max_drawdown: float
    avg_tp_time: float
    avg_sl_time: float
    avg_duration: float
    reliability: str = "unknown"  # green / yellow / red

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _max_consecutive(values: Iterable[bool]) -> int:
    """Count max streak of True values in a boolean sequence."""
    best = cur = 0
    for v in values:
        if v:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _equity_curve(pnls: List[float]) -> List[float]:
    eq = [0.0]
    for p in pnls:
        eq.append(eq[-1] + p)
    return eq


def _max_drawdown(eq: List[float]) -> float:
    peak = eq[0]
    dd = 0.0
    for v in eq:
        if v > peak:
            peak = v
        dd = min(dd, v - peak)
    return dd


def _compute_combo_stats(results: List[SimResult], min_trades: int, low_data_trades: int) -> ComboStats:
    pnls = [r.pnl for r in results]
    wins = [r for r in results if r.pnl > 0]
    losses = [r for r in results if r.pnl < 0]
    be = [r for r in results if r.pnl == 0]
    n = len(results)

    win_seq = [r.pnl > 0 for r in results]
    loss_seq = [r.pnl < 0 for r in results]

    gross_wins = sum(r.pnl for r in wins)
    gross_losses = abs(sum(r.pnl for r in losses))
    pf = gross_wins / gross_losses if gross_losses > 0 else (999.0 if gross_wins > 0 else 0.0)

    eq = _equity_curve(pnls)
    mdd = _max_drawdown(eq)

    tp_times = [r.hold_seconds for r in results if r.exit_type == "TP"]
    sl_times = [r.hold_seconds for r in results if r.exit_type == "SL"]
    all_durations = [r.hold_seconds for r in results]

    if n >= min_trades:
        reliability = "green"
    elif n >= low_data_trades:
        reliability = "yellow"
    else:
        reliability = "red"

    return ComboStats(
        tp=results[0].tp,
        sl=results[0].sl,
        trades=n,
        wins=len(wins),
        losses=len(losses),
        breakeven=len(be),
        win_rate=len(wins) / n * 100 if n else 0.0,
        loss_rate=len(losses) / n * 100 if n else 0.0,
        tp_hits=sum(1 for r in results if r.tp_hit),
        sl_hits=sum(1 for r in results if r.sl_hit),
        tp_hit_rate=sum(1 for r in results if r.tp_hit) / n * 100 if n else 0.0,
        sl_hit_rate=sum(1 for r in results if r.sl_hit) / n * 100 if n else 0.0,
        avg_pnl=float(np.mean(pnls)) if n else 0.0,
        median_pnl=float(np.median(pnls)) if n else 0.0,
        total_pnl=sum(pnls),
        profit_factor=pf,
        expectancy=sum(pnls) / n if n else 0.0,
        avg_win=float(np.mean([r.pnl for r in wins])) if wins else 0.0,
        avg_loss=float(np.mean([r.pnl for r in losses])) if losses else 0.0,
        max_win_streak=_max_consecutive(win_seq),
        max_loss_streak=_max_consecutive(loss_seq),
        max_drawdown=mdd,
        avg_tp_time=float(np.mean(tp_times)) if tp_times else 0.0,
        avg_sl_time=float(np.mean(sl_times)) if sl_times else 0.0,
        avg_duration=float(np.mean(all_durations)) if all_durations else 0.0,
        reliability=reliability,
    )


# ---------------------------------------------------------------------------
# Region detection
# ---------------------------------------------------------------------------
def _find_stable_regions(grid: pd.DataFrame, cfg: ResearchConfig) -> List[Dict[str, Any]]:
    """Find contiguous high-scoring cells in the (TP, SL) grid."""
    df = grid.copy()
    df["score"] = (
        df["profit_factor"].clip(lower=0)
        * df["total_pnl"].clip(lower=0)
        * (df["win_rate"] / 100.0)
    )
    score_cut = df["score"].quantile(0.85)
    df["good"] = (
        (df["trades"] >= cfg.min_trades)
        & (df["profit_factor"] >= cfg.pf_good)
        & (df["total_pnl"] > 0)
        & (df["expectancy"] > 0)
        & (df["score"] >= score_cut)
    )

    if df["good"].sum() == 0:
        return []

    # Build a matrix view for connected-component extraction.
    tp_sorted = sorted(df["tp"].unique())
    sl_sorted = sorted(df["sl"].unique())
    tp_i = {v: i for i, v in enumerate(tp_sorted)}
    sl_i = {v: i for i, v in enumerate(sl_sorted)}

    matrix = np.zeros((len(sl_sorted), len(tp_sorted)), dtype=bool)
    for _, row in df.iterrows():
        if row["good"]:
            matrix[sl_i[row["sl"]], tp_i[row["tp"]]] = True

    # 4-connected BFS.
    visited = set()
    regions: List[Dict[str, Any]] = []
    for r in range(matrix.shape[0]):
        for c in range(matrix.shape[1]):
            if not matrix[r, c] or (r, c) in visited:
                continue
            stack = [(r, c)]
            comp = set()
            while stack:
                cr, cc = stack.pop()
                if (cr, cc) in visited:
                    continue
                visited.add((cr, cc))
                comp.add((cr, cc))
                for dr, dc in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                    nr, nc = cr + dr, cc + dc
                    if 0 <= nr < matrix.shape[0] and 0 <= nc < matrix.shape[1] and matrix[nr, nc]:
                        stack.append((nr, nc))

            if len(comp) < cfg.region_min_combo:
                continue

            tps = [tp_sorted[cc] for _, cc in comp]
            sls = [sl_sorted[cr] for cr, _ in comp]
            subset = df[df.apply(lambda x: (sl_i[x["sl"]], tp_i[x["tp"]]) in comp, axis=1)]
            total_trades = int(subset["trades"].sum())
            score = (
                float(subset["profit_factor"].mean())
                * max(0, float(subset["total_pnl"].mean()))
                * (float(subset["win_rate"].mean()) / 100)
            )
            regions.append({
                "tp_min": float(min(tps)),
                "tp_max": float(max(tps)),
                "sl_min": float(min(sls)),
                "sl_max": float(max(sls)),
                "cells": len(comp),
                "trades_in_region": total_trades,
                "avg_pf": round(float(subset["profit_factor"].mean()), 3),
                "avg_expectancy": round(float(subset["expectancy"].mean()), 2),
                "avg_win_rate": round(float(subset["win_rate"].mean()), 2),
                "avg_total_pnl": round(float(subset["total_pnl"].mean()), 2),
                "max_drawdown": round(float(subset["max_drawdown"].min()), 2),
                "score": round(score, 4),
            })

    regions.sort(key=lambda x: x["score"], reverse=True)
    return regions


# ---------------------------------------------------------------------------
# Heatmap HTML
# ---------------------------------------------------------------------------
def _color(value: float, vmin: float, vmax: float, good_high: bool = True) -> str:
    if vmax == vmin:
        t = 0.5
    else:
        t = (value - vmin) / (vmax - vmin)
        t = max(0.0, min(1.0, t))
    if good_high:
        hue = 120 * t
    else:
        hue = 120 * (1 - t)
    return f"hsl({hue:.0f}, 70%, 85%)"


def _render_heatmap_html(grid: pd.DataFrame, output_path: Path) -> None:
    metrics = ["profit_factor", "expectancy", "total_pnl", "win_rate", "max_drawdown"]
    metric_names = {
        "profit_factor": "Profit Factor",
        "expectancy": "Expectancy ($)",
        "total_pnl": "Total PnL ($)",
        "win_rate": "Win Rate (%)",
        "max_drawdown": "Max Drawdown ($)",
    }

    html = [
        "<!DOCTYPE html>",
        "<html><head>",
        '<meta charset="utf-8">',
        "<title>TP/SL Heatmaps</title>",
        "<style>",
        "body{font-family:Arial,Helvetica,sans-serif;font-size:13px;padding:20px}",
        "h2{margin-top:30px}",
        "table{border-collapse:collapse;margin-bottom:20px}",
        "th,td{width:55px;text-align:center;padding:4px;border:1px solid #ccc;font-size:11px}",
        "th{background:#f0f0f0}",
        ".label{font-weight:bold;background:#fafafa}",
        "</style></head><body>",
        "<h1>TP/SL Research — Heatmaps</h1>",
    ]

    for m in metrics:
        html.append(f"<h2>{metric_names[m]}</h2>")
        pivot = grid.pivot(index="sl", columns="tp", values=m)
        if pivot.empty:
            html.append("<p>Not enough data for this metric.</p>")
            continue

        values = grid[m].dropna()
        if values.empty:
            html.append("<p>Not enough data for this metric.</p>")
            continue
        vmin, vmax = values.min(), values.max()
        good_high = m != "max_drawdown"

        html.append("<table>")
        # Header row: tp values.
        html.append("<tr><th>SL \\ TP</th>" + "".join(f"<th>{c:.2f}%</th>" for c in pivot.columns) + "</tr>")
        for sl, row in pivot.iterrows():
            html.append(f"<tr><th class='label'>{sl:.2f}%</th>")
            for tp in pivot.columns:
                v = row.get(tp)
                if pd.isna(v):
                    html.append("<td style='background:#eee'>-</td>")
                else:
                    bg = _color(float(v), float(vmin), float(vmax), good_high)
                    html.append(f"<td style='background:{bg}'>{v:.2f}</td>")
            html.append("</tr>")
        html.append("</table>")

    html.append("</body></html>")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html))


# ---------------------------------------------------------------------------
# Condition analysis
# ---------------------------------------------------------------------------
def _condition_label(trade: Trade, cond: str) -> Optional[str]:
    if cond == "side":
        return trade.side
    if cond == "regime":
        return str(trade.signal.get("regime", "unknown")) or "unknown"
    if cond == "time_of_day":
        h = datetime.fromtimestamp(trade.opened_ts, tz=timezone.utc).hour
        if 0 <= h < 8:
            return "asia"
        if 8 <= h < 16:
            return "europe"
        return "us"
    if cond == "confidence":
        c = _to_float(trade.signal.get("confidence"))
        if c >= 0.85:
            return "high"
        if c >= 0.65:
            return "mid"
        return "low"
    if cond == "volatility":
        atr = _to_float(trade.signal.get("atr"))
        # ATR relative to entry when available.
        if trade.entry_price > 0 and atr > 0:
            rel = atr / trade.entry_price * 100
            if rel >= 1.5:
                return "high"
            if rel >= 0.8:
                return "mid"
        return "low"
    if cond == "day_of_week":
        return datetime.fromtimestamp(trade.opened_ts, tz=timezone.utc).strftime("%A")
    return None


def _conditions_summary(trades: List[Trade], combo_stats: Dict[Tuple[float, float], ComboStats],
                        cfg: ResearchConfig) -> Dict[str, Any]:
    """For each condition, pick a robust TP/SL region."""
    conditions = ["side", "regime", "time_of_day", "confidence", "volatility"]
    summary: Dict[str, Any] = {}
    for cond in conditions:
        groups: Dict[str, List[Trade]] = defaultdict(list)
        for t in trades:
            label = _condition_label(t, cond)
            if label:
                groups[label].append(t)

        cond_result: Dict[str, Any] = {}
        for label, g in groups.items():
            if len(g) < cfg.min_trades:
                cond_result[label] = {"status": "too_few_trades", "n": len(g)}
                continue
            # Build grid for this group using cached combo stats is not possible
            # because stats depend on that trade subset. Re-run grid later in main.
            cond_result[label] = {"status": "computed_separately", "n": len(g)}
        summary[cond] = cond_result
    return summary


# ---------------------------------------------------------------------------
# Walk-forward
# ---------------------------------------------------------------------------
def _walk_forward(trades: List[Trade], loader: OhlcvLoader, cfg: ResearchConfig) -> List[Dict[str, Any]]:
    if len(trades) < cfg.n_walk_forward_folds * cfg.min_trades:
        return []

    trades_sorted = sorted(trades, key=lambda t: t.opened_ts)
    fold_size = max(1, len(trades_sorted) // cfg.n_walk_forward_folds)
    folds = [trades_sorted[i * fold_size:(i + 1) * fold_size] for i in range(cfg.n_walk_forward_folds)]

    results = []
    for i in range(len(folds) - 1):
        train = folds[i]
        test = folds[i + 1]
        train_grid = _build_grid(train, loader, cfg)
        test_grid = _build_grid(test, loader, cfg)
        regions = _find_stable_regions(train_grid, cfg)
        top = regions[:3]

        test_summary = []
        for r in top:
            # Evaluate the same region bounds on the next fold.
            subset = test_grid[
                (test_grid["tp"] >= r["tp_min"])
                & (test_grid["tp"] <= r["tp_max"])
                & (test_grid["sl"] >= r["sl_min"])
                & (test_grid["sl"] <= r["sl_max"])
                & (test_grid["trades"] >= cfg.min_trades)
            ]
            if not subset.empty:
                test_summary.append({
                    "region": f"TP {r['tp_min']}-{r['tp_max']}%, SL {r['sl_min']}-{r['sl_max']}%",
                    "test_pf": round(float(subset["profit_factor"].mean()), 3),
                    "test_win_rate": round(float(subset["win_rate"].mean()), 2),
                    "test_pnl": round(float(subset["total_pnl"].mean()), 2),
                    "test_trades": int(subset["trades"].sum()),
                    "stable": bool(float(subset["profit_factor"].mean()) >= cfg.pf_good),
                })
        results.append({
            "fold": i + 1,
            "train_range": _ts_range(train),
            "test_range": _ts_range(test),
            "train_regions": top,
            "test_summary": test_summary,
        })
    return results


def _ts_range(trades: List[Trade]) -> str:
    if not trades:
        return ""
    t0 = min(t.opened_ts for t in trades)
    t1 = max(t.opened_ts for t in trades)
    return f"{datetime.fromtimestamp(t0, tz=timezone.utc):%Y-%m-%d} -> {datetime.fromtimestamp(t1, tz=timezone.utc):%Y-%m-%d}"


# ---------------------------------------------------------------------------
# Grid building
# ---------------------------------------------------------------------------
def _build_grid(trades: List[Trade], loader: OhlcvLoader, cfg: ResearchConfig) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    combo_results: Dict[Tuple[float, float], List[SimResult]] = defaultdict(list)

    # Pre-compute candles per trade.
    hold_sec = cfg.max_hold_hours * 3600
    for t in trades:
        candles = loader.load_for_trade(t, hold_sec)
        if candles.empty:
            continue
        for tp in cfg.tp_values:
            for sl in cfg.sl_values:
                r = simulate_trade(t, candles, tp, sl)
                combo_results[(tp, sl)].append(r)

    for (tp, sl), results in combo_results.items():
        st = _compute_combo_stats(results, cfg.min_trades, cfg.low_data_trades)
        rows.append(st.as_dict())

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# MFE/MAE report
# ---------------------------------------------------------------------------
def _mfe_mae_report(trades: List[Trade], loader: OhlcvLoader) -> Dict[str, Any]:
    hold_sec = 48 * 3600
    long_mfe, long_mae = [], []
    short_mfe, short_mae = [], []
    for t in trades:
        candles = loader.load_for_trade(t, hold_sec)
        if candles.empty:
            continue
        mfe, mae = compute_mfe_mae(t, candles)
        if t.side == "long":
            long_mfe.append(mfe)
            long_mae.append(mae)
        else:
            short_mfe.append(mfe)
            short_mae.append(mae)

    def pct(arr: List[float]) -> Dict[str, float]:
        if not arr:
            return {}
        a = np.array(arr)
        return {
            "count": int(len(arr)),
            "mean": round(float(np.mean(a)), 4),
            "median": round(float(np.median(a)), 4),
            **{f"p{p}": round(float(np.percentile(a, p)), 4) for p in [25, 50, 75, 80, 90, 95]},
        }

    return {
        "long_mfe_pct": pct(long_mfe),
        "long_mae_pct": pct(long_mae),
        "short_mfe_pct": pct(short_mfe),
        "short_mae_pct": pct(short_mae),
    }


# ---------------------------------------------------------------------------
# Top table
# ---------------------------------------------------------------------------
def _top_table(grid: pd.DataFrame, by: str = "score", n: int = 10,
               min_trades: int = 30) -> pd.DataFrame:
    g = grid[grid["trades"] >= min_trades].copy()
    if g.empty:
        return pd.DataFrame()
    g["score"] = (
        g["profit_factor"].clip(lower=0)
        * g["total_pnl"].clip(lower=0)
        * (g["win_rate"] / 100.0)
    )
    return g.sort_values(by, ascending=False).head(n)


# ---------------------------------------------------------------------------
# Main research runner
# ---------------------------------------------------------------------------
class TpSlResearch:
    """High-level entry point."""

    def __init__(self, config: ResearchConfig):
        self.cfg = config
        self.loader = OhlcvLoader(Path(config.cache_dir), config.timeframe)

    def run(self, trades: List[Trade]) -> Dict[str, Any]:
        if not trades:
            raise ValueError("No trades to analyse.")

        print(f"[RESEARCH] Loaded {len(trades)} trades")
        print(f"[RESEARCH] Simulating TP={self.cfg.tp_values} x SL={self.cfg.sl_values} on {self.cfg.timeframe} data")

        # 1. Full grid.
        grid = _build_grid(trades, self.loader, self.cfg)
        print(f"[RESEARCH] Grid built: {len(grid)} (TP x SL) combinations")

        # 2. Stable regions.
        regions = _find_stable_regions(grid, self.cfg)

        # 3. MFE/MAE.
        mfe_mae = _mfe_mae_report(trades, self.loader)

        # 4. Condition analysis — perform per-condition grid search.
        conditions = ["side", "regime", "time_of_day", "confidence", "volatility"]
        condition_best: Dict[str, Any] = {}
        for cond in conditions:
            groups: Dict[str, List[Trade]] = defaultdict(list)
            for t in trades:
                label = _condition_label(t, cond)
                if label:
                    groups[label].append(t)

            cond_result: Dict[str, Any] = {}
            for label, g in groups.items():
                if len(g) < self.cfg.min_trades:
                    cond_result[label] = {"status": "insufficient_data", "n": len(g)}
                    continue
                sub_grid = _build_grid(g, self.loader, self.cfg)
                top = _top_table(sub_grid, min_trades=max(5, self.cfg.min_trades // 3)).head(3)
                sub_regions = _find_stable_regions(sub_grid, self.cfg)
                cond_result[label] = {
                    "n": len(g),
                    "top3": top[["tp", "sl", "trades", "win_rate", "profit_factor", "expectancy", "total_pnl", "max_drawdown"]].to_dict(orient="records") if not top.empty else [],
                    "stable_regions": sub_regions[:2],
                }
            condition_best[cond] = cond_result

        # 5. Walk-forward.
        wf = _walk_forward(trades, self.loader, self.cfg)

        # 6. Overall top table.
        top10 = _top_table(grid, min_trades=self.cfg.min_trades).head(10)

        report = {
            "meta": {
                "trades": len(trades),
                "symbols": sorted({t.symbol for t in trades}),
                "tp_values": self.cfg.tp_values,
                "sl_values": self.cfg.sl_values,
                "timeframe": self.cfg.timeframe,
                "fee_rate_per_side": self.cfg.fee_rate,
                "min_trades_threshold": self.cfg.min_trades,
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            },
            "top10": top10.to_dict(orient="records") if not top10.empty else [],
            "stable_regions": regions[:10],
            "mfe_mae_percentiles": mfe_mae,
            "conditions": condition_best,
            "walk_forward": wf,
            "all_combos": grid.to_dict(orient="records"),
        }
        return report


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------
def _format_report(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    meta = report["meta"]
    lines.append("=" * 70)
    lines.append("TP / SL RESEARCH REPORT")
    lines.append("=" * 70)
    lines.append(f"Trades analysed: {meta['trades']}")
    lines.append(f"Symbols: {', '.join(meta['symbols'])}")
    lines.append(f"Timeframe: {meta['timeframe']}   Fee rate (per side): {meta['fee_rate_per_side']*100:.4f}%")
    lines.append(f"TP grid: {meta['tp_values']}")
    lines.append(f"SL grid: {meta['sl_values']}")
    lines.append("")

    lines.append("TOP TP/SL (by composite score)")
    lines.append("-" * 70)
    lines.append(f"{'Rank':>4} {'TP%':>6} {'SL%':>6} {'Trades':>7} {'Win%':>7} {'PF':>6} {'Expect $':>10} {'PnL $':>12} {'MaxDD $':>10}")
    for i, row in enumerate(report["top10"], 1):
        lines.append(
            f"{i:>4} {row['tp']:>6.2f} {row['sl']:>6.2f} "
            f"{row['trades']:>7} {row['win_rate']:>7.2f} {row['profit_factor']:>6.2f} "
            f"{row['expectancy']:>10.2f} {row['total_pnl']:>12.2f} {row['max_drawdown']:>10.2f}"
        )

    lines.append("")
    lines.append("STABLE REGIONS")
    lines.append("-" * 70)
    for r in report["stable_regions"][:5]:
        lines.append(
            f"TP {r['tp_min']:.2f}-{r['tp_max']:.2f}%  |  "
            f"SL {r['sl_min']:.2f}-{r['sl_max']:.2f}%  |  "
            f"cells={r['cells']}  avg PF={r['avg_pf']}  "
            f"avg WR={r['avg_win_rate']:.1f}%  "
            f"avg PnL=${r['avg_total_pnl']:.2f}  "
            f"MaxDD=${r['max_drawdown']:.2f}"
        )
    if not report["stable_regions"]:
        lines.append("No stable regions found with current thresholds.")

    lines.append("")
    lines.append("MFE / MAE PERCENTILES (%)")
    lines.append("-" * 70)
    for key in ["long_mfe_pct", "long_mae_pct", "short_mfe_pct", "short_mae_pct"]:
        data = report["mfe_mae_percentiles"].get(key, {})
        if not data:
            continue
        s = f"{key}: count={data.get('count')} mean={data.get('mean')} "
        s += " ".join(f"{k}={v}" for k, v in data.items() if k not in ("count", "mean"))
        lines.append(s)

    lines.append("")
    lines.append("BEST BY CONDITION")
    lines.append("-" * 70)
    for cond, groups in report["conditions"].items():
        lines.append(f"[{cond}]")
        for label, info in groups.items():
            if info.get("status") == "insufficient_data":
                lines.append(f"  {label}: n={info['n']} — too few trades")
            elif info.get("top3"):
                lines.append(f"  {label}: n={info['n']}")
                for t in info["top3"][:2]:
                    lines.append(
                        f"    TP {t['tp']:.2f}%  SL {t['sl']:.2f}%  "
                        f"trades={t['trades']}  PF={t['profit_factor']:.2f}  "
                        f"WR={t['win_rate']:.1f}%  PnL=${t['total_pnl']:.2f}"
                    )

    lines.append("")
    lines.append("WALK-FORWARD STABILITY")
    lines.append("-" * 70)
    if not report["walk_forward"]:
        lines.append("Not enough data for walk-forward split.")
    for w in report["walk_forward"]:
        lines.append(f"Fold {w['fold']}: train {w['train_range']} -> test {w['test_range']}")
        for t in w["test_summary"]:
            stable = "STABLE" if t["stable"] else "unstable"
            lines.append(
                f"  {t['region']}: test PF={t['test_pf']} "
                f"WR={t['test_win_rate']:.1f}%  PnL=${t['test_pnl']:.2f} "
                f"[{stable}]"
            )

    lines.append("")
    lines.append("=" * 70)
    lines.append("END OF REPORT")
    lines.append("=" * 70)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Virtual TP/SL research on historical trades.")
    parser.add_argument("--trades", type=Path, default=Path("logs/trades.jsonl"), help="Path to trades JSONL")
    parser.add_argument("--config", type=Path, help="JSON config to override defaults")
    parser.add_argument("--output", type=Path, default=Path("research/tp_sl_output"), help="Output prefix")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    cfg = ResearchConfig()
    if args.config and args.config.exists():
        with open(args.config, "r", encoding="utf-8") as f:
            cfg = ResearchConfig.from_dict(json.load(f))

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg.output_dir = str(output_dir)

    trades = load_trades(args.trades)
    research = TpSlResearch(cfg)
    report = research.run(trades)

    # Save JSON.
    json_path = output_dir / "tp_sl_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    # Save text.
    text_path = output_dir / "tp_sl_report.txt"
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(_format_report(report))

    # Save heatmap HTML.
    html_path = output_dir / "tp_sl_heatmap.html"
    _render_heatmap_html(pd.DataFrame(report["all_combos"]), html_path)

    print(f"\n[RESEARCH] Done. Outputs saved to:")
    print(f"  JSON:   {json_path}")
    print(f"  TEXT:   {text_path}")
    print(f"  HTML:   {html_path}")
    print(_format_report(report))


if __name__ == "__main__":
    main()
