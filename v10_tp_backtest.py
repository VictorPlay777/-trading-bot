#!/usr/bin/env python3
"""Backtest different TP strategies (with BE-stop @ 0.3R always on)."""

import json
from collections import defaultdict


TRADES_PATH = "logs/v10/trades_v10.jsonl"


def load_trades():
    out = []
    with open(TRADES_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return [t for t in out if t.get("mfe_r") is not None and t.get("exit_r") is not None]


def compute_atr_pct(t):
    sig = t.get("signal", {})
    atr = sig.get("atr") or 0
    entry = t.get("entry_price") or 0
    return (atr / entry) if (atr > 0 and entry > 0) else 0.0


def r_to_dollars(r_value, t):
    notional = t.get("notional_entry") or 10000
    atr_pct = compute_atr_pct(t)
    if atr_pct <= 0:
        return 0.0
    return r_value * 0.5 * atr_pct * notional


# === Strategy with TP variations + BE-stop @ 0.3R ===

def simulate(t, tp_r=1.0, be_arm_r=0.3, be_value_r=0.05, trailing_after_r=None, trail_dist_r=0.4):
    """Simulate exit with given TP, BE-stop, optional trailing.

    Assumptions:
    - If mfe_r >= tp_r: TP was hit -> exit at +tp_r
    - elif mfe_r >= be_arm_r and exit_r < be_value_r: BE-stop triggered -> exit at be_value_r
    - elif trailing_after_r is set and mfe_r >= trailing_after_r:
        SL trailing = mfe_r - trail_dist_r. Exit = max(actual_exit, trail_floor).
    - else: keep actual exit_r
    """
    mfe = t["mfe_r"]
    exit_r = t["exit_r"]

    # TP hit
    if mfe >= tp_r:
        return tp_r

    # Trailing engaged
    if trailing_after_r is not None and mfe >= trailing_after_r:
        trail_floor = mfe - trail_dist_r
        # If actual exit was higher than trail floor, keep it; else trail floor.
        return max(exit_r, trail_floor, be_value_r if mfe >= be_arm_r else exit_r)

    # BE-stop fires when MFE armed but exit reversed below BE
    if mfe >= be_arm_r and exit_r < be_value_r:
        return be_value_r

    return exit_r


def evaluate(trades, sim_fn, name):
    n = wins = losses = 0
    total_r = total_d = 0.0
    by_side = defaultdict(lambda: {"n": 0, "$": 0.0})
    for t in trades:
        new_r = sim_fn(t)
        n += 1
        if new_r > 0: wins += 1
        elif new_r < 0: losses += 1
        total_r += new_r
        d = r_to_dollars(new_r, t)
        total_d += d
        side = t.get("direction", "?")
        by_side[side]["n"] += 1
        by_side[side]["$"] += d
    wr = wins / n * 100 if n else 0
    print(f"\n=== {name} ===")
    print(f"  WR: {wr:.1f}% ({wins}W/{losses}L)")
    print(f"  Total R: {total_r:+.2f}   Total $: ${total_d:+,.2f}")
    print(f"  Avg $/trade: ${total_d/n:+,.2f}")
    for side, s in sorted(by_side.items()):
        avg = s["$"] / s["n"] if s["n"] else 0
        print(f"  [{side}] n={s['n']:3d}  total=${s['$']:+8.2f}  avg=${avg:+7.2f}")


def main():
    trades = load_trades()
    print(f"Loaded {len(trades)} trades with MFE/exit_r.")

    print("\n" + "=" * 70)
    print("TP STRATEGY BACKTEST (BE-stop @ 0.3R always on)")
    print("=" * 70)

    evaluate(trades, lambda t: simulate(t, tp_r=1.0), "BASELINE: TP=1R + BE@0.3R (current V10c)")

    # TP variations
    for tp in [0.5, 0.7, 0.8, 1.2, 1.5, 2.0, 3.0]:
        evaluate(trades, lambda t, tp=tp: simulate(t, tp_r=tp), f"TP={tp}R + BE@0.3R")

    # Trailing variants (TP=large = effectively no TP)
    print("\n--- TRAILING STRATEGIES (TP=3R = practically no TP) ---")
    for trail_after_loop, trail_dist_loop in [(0.5, 0.3), (0.8, 0.4), (1.0, 0.5), (0.5, 0.2), (0.3, 0.15)]:
        ta = trail_after_loop
        td = trail_dist_loop
        evaluate(
            trades,
            (lambda ta_=ta, td_=td: lambda t: simulate(t, tp_r=3.0, trailing_after_r=ta_, trail_dist_r=td_))(),
            f"TP=3R + BE@0.3R + TRAIL after {ta}R, dist {td}R",
        )

    # Combined: lower TP + trailing
    print("\n--- COMBINED (TP + trailing) ---")
    for tp_loop, ta_loop, td_loop in [(1.5, 0.8, 0.3), (1.0, 0.5, 0.3), (2.0, 1.0, 0.4), (1.2, 0.6, 0.25)]:
        tp = tp_loop
        ta = ta_loop
        td = td_loop
        evaluate(
            trades,
            (lambda tp_=tp, ta_=ta, td_=td: lambda t: simulate(t, tp_r=tp_, trailing_after_r=ta_, trail_dist_r=td_))(),
            f"TP={tp}R + BE@0.3R + TRAIL after {ta}R, dist {td}R",
        )


if __name__ == "__main__":
    main()
