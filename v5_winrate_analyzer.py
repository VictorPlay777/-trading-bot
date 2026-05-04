#!/usr/bin/env python3
"""
v5 Winrate Analyzer
Analyzes trades.jsonl for winrate by:
- Symbol (per-coin)
- Confidence bucket (0.70-0.80, 0.80-0.90, 0.90-1.00)
- Direction (long/short)
- Combined: symbol + confidence

Usage:
    python v5_winrate_analyzer.py [trades.jsonl path]
    # or from server:
    python3 v5_winrate_analyzer.py logs/trades.jsonl
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from decimal import Decimal


def load_trades(filepath: str):
    """Load trade records from JSONL."""
    trades = []
    path = Path(filepath)
    if not path.exists():
        print(f"[ERROR] File not found: {filepath}")
        return []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("schema") != "selective_trade_v1":
                    continue
                trades.append(rec)
            except json.JSONDecodeError:
                continue
    return trades


def confidence_bucket(conf: float) -> str:
    if conf >= 0.90:
        return "0.90-1.00"
    elif conf >= 0.80:
        return "0.80-0.90"
    elif conf >= 0.70:
        return "0.70-0.80"
    else:
        return "0.00-0.70"


def analyze_winrate(trades):
    """Compute winrate statistics."""
    if not trades:
        print("[INFO] No trades found.")
        return

    # Overall stats
    wins = sum(1 for t in trades if t.get("realized_pnl_net", 0) > 0)
    losses = sum(1 for t in trades if t.get("realized_pnl_net", 0) <= 0)
    total = wins + losses
    wr = (wins / total * 100) if total > 0 else 0
    total_pnl = sum(t.get("realized_pnl_net", 0) for t in trades)
    avg_pnl = total_pnl / total if total > 0 else 0

    print(f"\n{'='*60}")
    print(f"  v5 WINRATE ANALYZER — {len(trades)} trades")
    print(f"{'='*60}")
    print(f"\n  OVERALL:")
    print(f"    Wins:   {wins}  |  Losses: {losses}  |  Total: {total}")
    print(f"    Winrate: {wr:.1f}%")
    print(f"    Total PnL: {total_pnl:.2f} USDT  |  Avg per trade: {avg_pnl:.2f}")

    # By Symbol
    print(f"\n  BY SYMBOL:")
    print(f"    {'Symbol':<12} {'W':>4} {'L':>4} {'WR%':>6} {'Avg PnL':>10} {'Total PnL':>12}")
    print(f"    {'-'*54}")
    by_sym = defaultdict(list)
    for t in trades:
        by_sym[t.get("symbol", "unknown")].append(t)

    for sym in sorted(by_sym.keys()):
        ts = by_sym[sym]
        w = sum(1 for t in ts if t.get("realized_pnl_net", 0) > 0)
        l = len(ts) - w
        wr_sym = (w / len(ts) * 100) if ts else 0
        pnl = sum(t.get("realized_pnl_net", 0) for t in ts)
        avg = pnl / len(ts) if ts else 0
        print(f"    {sym:<12} {w:>4} {l:>4} {wr_sym:>6.1f} {avg:>10.2f} {pnl:>12.2f}")

    # By Confidence
    print(f"\n  BY CONFIDENCE:")
    print(f"    {'Bucket':<12} {'W':>4} {'L':>4} {'WR%':>6} {'Avg PnL':>10} {'Total PnL':>12}")
    print(f"    {'-'*54}")
    by_conf = defaultdict(list)
    for t in trades:
        conf = float(t.get("signal", {}).get("confidence", 0) or 0)
        by_conf[confidence_bucket(conf)].append(t)

    for bucket in ["0.90-1.00", "0.80-0.90", "0.70-0.80", "0.00-0.70"]:
        ts = by_conf.get(bucket, [])
        if not ts:
            continue
        w = sum(1 for t in ts if t.get("realized_pnl_net", 0) > 0)
        l = len(ts) - w
        wr_conf = (w / len(ts) * 100) if ts else 0
        pnl = sum(t.get("realized_pnl_net", 0) for t in ts)
        avg = pnl / len(ts) if ts else 0
        print(f"    {bucket:<12} {w:>4} {l:>4} {wr_conf:>6.1f} {avg:>10.2f} {pnl:>12.2f}")

    # By Direction
    print(f"\n  BY DIRECTION:")
    print(f"    {'Dir':<8} {'W':>4} {'L':>4} {'WR%':>6} {'Avg PnL':>10} {'Total PnL':>12}")
    print(f"    {'-'*50}")
    by_dir = defaultdict(list)
    for t in trades:
        by_dir[t.get("direction", "unknown")].append(t)
    for d in ["long", "short"]:
        ts = by_dir.get(d, [])
        if not ts:
            continue
        w = sum(1 for t in ts if t.get("realized_pnl_net", 0) > 0)
        l = len(ts) - w
        wr_dir = (w / len(ts) * 100) if ts else 0
        pnl = sum(t.get("realized_pnl_net", 0) for t in ts)
        avg = pnl / len(ts) if ts else 0
        print(f"    {d:<8} {w:>4} {l:>4} {wr_dir:>6.1f} {avg:>10.2f} {pnl:>12.2f}")

    # Symbol + Confidence matrix (top 10 symbols by trade count)
    print(f"\n  SYMBOL + CONFIDENCE MATRIX (top symbols):")
    top_syms = sorted(by_sym.keys(), key=lambda s: len(by_sym[s]), reverse=True)[:10]
    print(f"    {'Symbol':<12} {'0.90+':>8} {'0.80-0.90':>10} {'0.70-0.80':>10} {'<0.70':>8}")
    print(f"    {'-'*54}")
    for sym in top_syms:
        ts = by_sym[sym]
        buckets = defaultdict(lambda: {"w": 0, "l": 0})
        for t in ts:
            conf = float(t.get("signal", {}).get("confidence", 0) or 0)
            b = confidence_bucket(conf)
            if t.get("realized_pnl_net", 0) > 0:
                buckets[b]["w"] += 1
            else:
                buckets[b]["l"] += 1

        def fmt(b):
            d = buckets.get(b, {"w": 0, "l": 0})
            total = d["w"] + d["l"]
            if total == 0:
                return "—"
            wr = d["w"] / total * 100
            return f"{wr:.0f}% ({total})"

        print(f"    {sym:<12} {fmt('0.90-1.00'):>8} {fmt('0.80-0.90'):>10} {fmt('0.70-0.80'):>10} {fmt('0.00-0.70'):>8}")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    filepath = sys.argv[1] if len(sys.argv) > 1 else "logs/trades.jsonl"
    trades = load_trades(filepath)
    analyze_winrate(trades)
