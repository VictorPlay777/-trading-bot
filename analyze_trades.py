#!/usr/bin/env python3
"""
Analyze trading performance from selective_ml_bot trades.jsonl
"""
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone

def load_trades(path="logs/trades.jsonl"):
    trades = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    trades.append(json.loads(line))
                except Exception:
                    continue
    except FileNotFoundError:
        print(f"File not found: {path}")
        return []
    return trades

def analyze_trades(trades):
    if not trades:
        print("No trades to analyze.")
        return
    
    # Time range
    min_ts = min(t.get("opened_ts", 0) for t in trades)
    max_ts = max(t.get("closed_ts", 0) for t in trades)
    print("=" * 70)
    print("SELECTIVE ML BOT - TRADE ANALYSIS REPORT")
    print("=" * 70)
    print(f"Period: {datetime.fromtimestamp(min_ts, tz=timezone.utc).isoformat()[:19]}Z")
    print(f"        to {datetime.fromtimestamp(max_ts, tz=timezone.utc).isoformat()[:19]}Z")
    print(f"Total closed trades: {len(trades)}")
    
    # Overall PnL
    total_pnl = sum(t.get("realized_pnl_net", 0) for t in trades)
    winners = [t for t in trades if t.get("realized_pnl_net", 0) > 0]
    losers = [t for t in trades if t.get("realized_pnl_net", 0) <= 0]
    
    print(f"\n💰 P&L SUMMARY:")
    print(f"  Total PnL: ${total_pnl:,.2f}")
    print(f"  Winning trades: {len(winners)} ({len(winners)/len(trades)*100:.1f}%)")
    print(f"  Losing trades: {len(losers)} ({len(losers)/len(trades)*100:.1f}%)")
    
    if winners:
        avg_win = sum(t.get("realized_pnl_net", 0) for t in winners) / len(winners)
        max_win = max(t.get("realized_pnl_net", 0) for t in winners)
        print(f"  Average win: +${avg_win:,.2f} | Max: +${max_win:,.2f}")
    if losers:
        avg_loss = sum(t.get("realized_pnl_net", 0) for t in losers) / len(losers)
        max_loss = min(t.get("realized_pnl_net", 0) for t in losers)
        print(f"  Average loss: ${avg_loss:,.2f} | Max loss: ${max_loss:,.2f}")
    
    # Expectancy
    expectancy = total_pnl / len(trades) if trades else 0
    print(f"\n📊 EXPECTANCY: ${expectancy:.2f} per trade")
    
    # By symbol
    print("\n💱 BY SYMBOL:")
    by_symbol = defaultdict(list)
    for t in trades:
        sym = t.get("symbol", "unknown")
        by_symbol[sym].append(t)
    for sym, group in sorted(by_symbol.items(), key=lambda x: sum(t.get("realized_pnl_net", 0) for t in x[1]), reverse=True):
        wins = len([t for t in group if t.get("realized_pnl_net", 0) > 0])
        pnl = sum(t.get("realized_pnl_net", 0) for t in group)
        avg_dur = sum(t.get("duration_sec", 0) for t in group) / len(group) if group else 0
        print(f"  {sym:12s}: {len(group):3d} trades | {wins/len(group)*100:5.1f}% WR | PnL=${pnl:+8.2f} | avg_dur={int(avg_dur/60)}min")

    # By regime
    print("\n📈 BY REGIME:")
    by_regime = defaultdict(list)
    for t in trades:
        reg = t.get("signal", {}).get("regime", "unknown")
        by_regime[reg].append(t)
    for reg, group in sorted(by_regime.items(), key=lambda x: len(x[1]), reverse=True):
        wins = len([t for t in group if t.get("realized_pnl_net", 0) > 0])
        pnl = sum(t.get("realized_pnl_net", 0) for t in group)
        avg_dur = sum(t.get("duration_sec", 0) for t in group) / len(group) if group else 0
        print(f"  {reg:10s}: {len(group):3d} trades | {wins/len(group)*100:5.1f}% WR | PnL=${pnl:+.2f} | avg_dur={int(avg_dur/60)}min")
    
    # By confidence bucket
    print("\n🎯 BY CONFIDENCE (conf):")
    buckets = [
        (">=0.80", lambda x: x >= 0.80),
        ("0.70-0.80", lambda x: 0.70 <= x < 0.80),
        ("0.60-0.70", lambda x: 0.60 <= x < 0.70),
        ("<0.60", lambda x: x < 0.60),
    ]
    for name, pred in buckets:
        group = [t for t in trades if pred(t.get("signal", {}).get("confidence", 0))]
        if group:
            wins = len([t for t in group if t.get("realized_pnl_net", 0) > 0])
            pnl = sum(t.get("realized_pnl_net", 0) for t in group)
            print(f"  {name:12s}: {len(group):3d} trades | {wins/len(group)*100:5.1f}% WR | PnL=${pnl:+.2f}")
    
    # By score bucket
    print("\n🎯 BY QUALITY (score):")
    sbuckets = [
        (">=0.70", lambda x: x >= 0.70),
        ("0.60-0.70", lambda x: 0.60 <= x < 0.70),
        ("0.55-0.60", lambda x: 0.55 <= x < 0.60),
        ("<0.55", lambda x: x < 0.55),
    ]
    for name, pred in sbuckets:
        group = [t for t in trades if pred(t.get("signal", {}).get("score", 0))]
        if group:
            wins = len([t for t in group if t.get("realized_pnl_net", 0) > 0])
            pnl = sum(t.get("realized_pnl_net", 0) for t in group)
            print(f"  {name:12s}: {len(group):3d} trades | {wins/len(group)*100:5.1f}% WR | PnL=${pnl:+.2f}")
    
    # By EV sign
    print("\n💡 BY EXPECTED VALUE (EV):")
    ev_pos = [t for t in trades if t.get("signal", {}).get("ev", 0) > 0]
    ev_neg = [t for t in trades if t.get("signal", {}).get("ev", 0) <= 0]
    if ev_pos:
        wins = len([t for t in ev_pos if t.get("realized_pnl_net", 0) > 0])
        pnl = sum(t.get("realized_pnl_net", 0) for t in ev_pos)
        print(f"  Positive EV: {len(ev_pos)} trades | {wins/len(ev_pos)*100:.1f}% WR | PnL=${pnl:+.2f}")
    if ev_neg:
        wins = len([t for t in ev_neg if t.get("realized_pnl_net", 0) > 0])
        pnl = sum(t.get("realized_pnl_net", 0) for t in ev_neg)
        print(f"  Negative EV: {len(ev_neg)} trades | {wins/len(ev_neg)*100:.1f}% WR | PnL=${pnl:+.2f}")
    
    # Recommendation
    print("\n📝 RECOMMENDATIONS (data-driven):")
    
    # Find best performing regime
    best_regime = max(by_regime.items(), key=lambda x: sum(t.get("realized_pnl_net", 0) for t in x[1]))
    if best_regime[1]:
        print(f"  • Focus on '{best_regime[0]}' regime (best PnL performance)")
    
    # Check chop vs trend
    if "chop" in by_regime and "trend" in by_regime:
        chop_wr = len([t for t in by_regime["chop"] if t.get("realized_pnl_net", 0) > 0]) / len(by_regime["chop"]) * 100
        trend_wr = len([t for t in by_regime["trend"] if t.get("realized_pnl_net", 0) > 0]) / len(by_regime["trend"]) * 100
        if trend_wr > chop_wr + 15:
            print(f"  • Trend ({trend_wr:.0f}% WR) significantly outperforms chop ({chop_wr:.0f}% WR)")
            print(f"  • Consider: raise chop threshold or reduce chop exposure")
        
    print("=" * 70)

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "logs/trades.jsonl"
    trades = load_trades(path)
    analyze_trades(trades)
