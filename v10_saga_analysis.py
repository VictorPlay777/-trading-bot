#!/usr/bin/env python3
"""Deep-dive analysis for SAGAUSDT trades."""

import json
from collections import Counter

TRADES_PATH = "logs/v10/trades_v10.jsonl"
SIGNALS_PATH = "logs/v10/signals_all.jsonl"


def load_trades(symbol=None):
    trades = []
    with open(TRADES_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            t = json.loads(line)
            if symbol and t.get("symbol") != symbol:
                continue
            trades.append(t)
    return trades


def load_signals(symbol=None):
    signals = []
    with open(SIGNALS_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            s = json.loads(line)
            if symbol and s.get("symbol") != symbol:
                continue
            signals.append(s)
    return signals


def analyze():
    print("=== SAGAUSDT DEEP DIVE ===\n")

    trades = load_trades("SAGAUSDT")
    print(f"Real trades: {len(trades)}\n")

    # Overall stats
    wins = [t for t in trades if t.get("realized_pnl_net", 0) > 0]
    losses = [t for t in trades if t.get("realized_pnl_net", 0) <= 0]
    total_pnl = sum(t.get("realized_pnl_net", 0) for t in trades)

    print(f"Wins: {len(wins)} | Losses: {len(losses)}")
    print(f"Total PnL: ${total_pnl:.2f}")
    print(f"Avg PnL: ${total_pnl/len(trades):.2f}")
    print(f"Avg Win: ${sum(t['realized_pnl_net'] for t in wins)/len(wins):.2f}" if wins else "No wins")
    print(f"Avg Loss: ${sum(t['realized_pnl_net'] for t in losses)/len(losses):.2f}" if losses else "No losses")
    print()

    # Per-trade breakdown
    print("=== Per-Trade Breakdown ===")
    print(f"{'Entry Time':<25} {'Side':<6} {'Entry':<12} {'Exit':<12} {'PnL':<10} {'MFE':<8} {'MAE':<8} {'Exit R':<8} {'Conf':<8} {'Regime':<8}")
    print("-" * 130)

    for t in trades:
        entry_ts = t.get("entry_timestamp", "")
        side = t.get("side", "")
        entry_p = t.get("entry_price", 0)
        exit_p = t.get("exit_price", 0)
        pnl = t.get("realized_pnl_net", 0)
        mfe_r = t.get("mfe_r", "")
        mae_r = t.get("mae_r", "")
        exit_r = t.get("exit_r", "")
        conf = t.get("signal", {}).get("confidence", "")
        regime = t.get("signal", {}).get("regime", "")

        entry_time = ""
        if entry_ts:
            import datetime
            entry_time = datetime.datetime.fromtimestamp(entry_ts, tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        print(f"{entry_time:<25} {side:<6} {entry_p:<12.6f} {exit_p:<12.6f} {pnl:<10.2f} {str(mfe_r):<8} {str(mae_r):<8} {str(exit_r):<8} {str(conf)[:6]:<8} {str(regime):<8}")

    print()

    # Signals (allowed + rejected)
    signals = load_signals("SAGAUSDT")
    allowed = [s for s in signals if s.get("allow")]
    rejected = [s for s in signals if not s.get("allow")]

    print(f"Signals: {len(signals)} total ({len(allowed)} allowed, {len(rejected)} rejected)")
    print()

    # Direction analysis
    sides = Counter(t.get("side") for t in trades)
    print(f"=== Direction ===")
    print(f"Long: {sides.get('long', 0)} | Short: {sides.get('short', 0)}")
    print()

    # Entry timing analysis
    print("=== Entry Timing Pattern ===")
    for t in trades:
        ts = t.get("entry_timestamp", 0)
        if ts:
            import datetime
            dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
            print(f"  {dt.strftime('%Y-%m-%d %H:%M UTC')} | {t['side']:<6} | ${t['realized_pnl_net']:.2f} | conf={t.get('signal',{}).get('confidence',''):.3f} | regime={t.get('signal',{}).get('regime','')}")

    print()

    # Price trajectory hypothesis
    print("=== Price Change at Entry ===")
    for t in trades:
        sig = t.get("signal", {})
        pc_1h = sig.get("price_change_1h", "N/A")
        pc_4h = sig.get("price_change_4h", "N/A")
        pc_24h = sig.get("price_change_24h", "N/A")
        print(f"  {t['side']:<6} | 1h={str(pc_1h)[:8]:<10} | 4h={str(pc_4h)[:8]:<10} | 24h={str(pc_24h)[:8]:<10} | PnL=${t['realized_pnl_net']:.2f}")


if __name__ == "__main__":
    analyze()
