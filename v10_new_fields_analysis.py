#!/usr/bin/env python3
"""Analyze new V10 fields: price_change_24h, hour_utc, day_of_week, trend_direction."""

import json
from collections import defaultdict


def load_signals():
    signals = []
    with open("logs/v10/signals_all.jsonl", "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                signals.append(json.loads(line))
            except:
                pass
    return signals


def load_trades():
    trades = []
    with open("logs/v10/trades_v10.jsonl", "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                trades.append(json.loads(line))
            except:
                pass
    return trades


def bucketize_signals_by_field(signals, field, bins):
    """Group signals by bucket of a numeric field, count outcomes."""
    buckets = defaultdict(lambda: {"long": 0, "short": 0, "allowed": 0})
    for s in signals:
        v = s.get(field)
        if v is None:
            continue
        # find bucket
        bucket = None
        for low, high, label in bins:
            if low <= v < high:
                bucket = label
                break
        if bucket is None:
            continue
        side = s.get("direction") or s.get("side")
        if side:
            buckets[bucket][side] += 1
        if s.get("allow"):
            buckets[bucket]["allowed"] += 1
    return buckets


def analyze_trades_by_signal_field(trades, field, bins):
    """Group trades by signal-time field, compute PnL."""
    buckets = defaultdict(lambda: {"n": 0, "wins": 0, "losses": 0, "pnl": 0.0, "long": 0, "short": 0})
    missing = 0
    for t in trades:
        sig = t.get("signal", {})
        v = sig.get(field)
        if v is None:
            missing += 1
            continue
        bucket = None
        for low, high, label in bins:
            if low <= v < high:
                bucket = label
                break
        if bucket is None:
            continue
        pnl = t.get("realized_pnl_net", 0)
        b = buckets[bucket]
        b["n"] += 1
        b["pnl"] += pnl
        if pnl > 0:
            b["wins"] += 1
        else:
            b["losses"] += 1
        side = t.get("direction")
        if side:
            b[side] += 1
    return buckets, missing


def print_table(title, buckets, bins):
    print(f"\n=== {title} ===")
    print(f"{'bucket':<20} {'n':>4} {'W/L':>10} {'WR':>7} {'PnL':>12} {'AvgPnL':>10} {'L/S':>10}")
    print("-" * 90)
    for low, high, label in bins:
        b = buckets.get(label)
        if not b or b["n"] == 0:
            continue
        wr = b["wins"] / b["n"] * 100 if b["n"] else 0
        avg = b["pnl"] / b["n"] if b["n"] else 0
        ls = "{}/{}".format(b["long"], b["short"])
        wl = "{}/{}".format(b["wins"], b["losses"])
        print("{:<20} {:>4} {:>10} {:>6.1f}% {:>+12.2f} {:>+10.2f} {:>10}".format(label, b["n"], wl, wr, b["pnl"], avg, ls))


def main():
    trades = load_trades()
    signals = load_signals()
    print(f"Loaded {len(trades)} trades, {len(signals)} signals")

    # Check what new fields are in signals
    if signals:
        sample = signals[0]
        print(f"\nSignal sample keys: {sorted(sample.keys())}")

    if trades:
        sample = trades[0]
        sig_keys = sorted(sample.get("signal", {}).keys())
        print(f"Trade.signal keys: {sig_keys}")

    # Price change 24h buckets
    pc_bins = [
        (-1.0, -0.20, "<-20% (crash)"),
        (-0.20, -0.10, "-20%..-10%"),
        (-0.10, -0.05, "-10%..-5%"),
        (-0.05, -0.02, "-5%..-2%"),
        (-0.02, 0.02, "-2%..+2% (flat)"),
        (0.02, 0.05, "+2%..+5%"),
        (0.05, 0.10, "+5%..+10%"),
        (0.10, 0.20, "+10%..+20%"),
        (0.20, 10.0, ">+20% (pump)"),
    ]
    buckets, miss = analyze_trades_by_signal_field(trades, "price_change_24h", pc_bins)
    print(f"\n(missing price_change_24h: {miss}/{len(trades)})")
    print_table("BY PRICE_CHANGE_24h", buckets, pc_bins)

    # Long-only and short-only price_change
    print("\n=== LONG TRADES BY PRICE_CHANGE_24h ===")
    long_trades = [t for t in trades if t.get("direction") == "long"]
    buckets, _ = analyze_trades_by_signal_field(long_trades, "price_change_24h", pc_bins)
    print_table("LONG ONLY", buckets, pc_bins)

    print("\n=== SHORT TRADES BY PRICE_CHANGE_24h ===")
    short_trades = [t for t in trades if t.get("direction") == "short"]
    buckets, _ = analyze_trades_by_signal_field(short_trades, "price_change_24h", pc_bins)
    print_table("SHORT ONLY", buckets, pc_bins)

    # Hour UTC
    hour_bins = [(h, h+1, f"hour_{h:02d}") for h in range(24)]
    buckets, miss = analyze_trades_by_signal_field(trades, "hour_utc", hour_bins)
    print(f"\n(missing hour_utc: {miss}/{len(trades)})")
    print_table("BY HOUR_UTC", buckets, hour_bins)

    # Day of week
    dow_bins = [(d, d+1, f"dow_{d}") for d in range(7)]
    buckets, miss = analyze_trades_by_signal_field(trades, "day_of_week", dow_bins)
    print(f"\n(missing day_of_week: {miss}/{len(trades)})")
    print_table("BY DAY_OF_WEEK", buckets, dow_bins)

    # ADX bucket
    adx_bins = [
        (0, 15, "ADX<15 (weak)"),
        (15, 20, "ADX 15-20"),
        (20, 25, "ADX 20-25"),
        (25, 30, "ADX 25-30"),
        (30, 40, "ADX 30-40"),
        (40, 100, "ADX 40+ (strong)"),
    ]
    buckets, miss = analyze_trades_by_signal_field(trades, "adx", adx_bins)
    print_table("BY ADX", buckets, adx_bins)


if __name__ == "__main__":
    main()
