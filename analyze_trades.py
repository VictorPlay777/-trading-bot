#!/usr/bin/env python3
"""
Analyze trading performance from selective_ml_bot trades.jsonl
"""
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from statistics import correlation

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

def fmt_ts(ts):
    if not ts:
        return "---"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%m-%d %H:%M:%S")

def analyze_trades(trades, verbose=True):
    if not trades:
        print("No trades to analyze.")
        return
    
    # Time range
    min_ts = min(t.get("opened_ts", 0) for t in trades)
    max_ts = max(t.get("closed_ts", 0) for t in trades)
    print("=" * 90)
    print("SELECTIVE ML BOT - FULL TRADE ANALYSIS REPORT")
    print("=" * 90)
    print(f"Period: {datetime.fromtimestamp(min_ts, tz=timezone.utc).isoformat()[:19]}Z")
    print(f"        to {datetime.fromtimestamp(max_ts, tz=timezone.utc).isoformat()[:19]}Z")
    print(f"Total closed trades: {len(trades)}")
    
    # --- DETAILED TRADE LOG A-Z ---
    if verbose:
        print("\n" + "=" * 90)
        print("FULL TRADE LOG (A to Z):")
        print("=" * 90)
        print(f"{'#':>3} {'OPENED':17} {'SYMBOL':12} {'SIDE':5} {'ENTRY':>10} {'QTY':>10} "
              f"{'PnL_NET':>9} {'FEES':>7} {'FUND':>6} {'DUR':>5} {'EXITS':25}")
        print("-" * 140)
        sorted_trades = sorted(trades, key=lambda t: t.get("opened_ts", 0))
        for i, t in enumerate(sorted_trades, 1):
            sym = t.get("symbol", "?")
            side = t.get("direction", "?")
            entry = t.get("entry_price", 0)
            qty = float(t.get("qty_total", 0) or 0)
            pnl = t.get("realized_pnl_net", 0)
            fees = t.get("entry_fees_est", 0) + t.get("exit_fees_est", 0)
            fund = t.get("funding_estimate", 0)
            dur_min = int(t.get("duration_sec", 0) / 60)
            # Compact exit reasons
            er = t.get("exit_reason_qty_sum", {}) or {}
            exit_summary = ",".join(f"{k}:{int(float(v))}" for k, v in sorted(er.items()))[:25]
            print(f"{i:3d} {fmt_ts(t.get('opened_ts')):17} {sym:12} {side:5} "
                  f"{entry:10.4f} {qty:10.2f} {pnl:+9.2f} {fees:7.2f} {fund:+6.2f} "
                  f"{dur_min:4d}m {exit_summary:25}")
    
    # --- PARTIAL CLOSES COUNT ---
    print("\n" + "=" * 90)
    print("PARTIAL CLOSES (TP/SL/TRAIL breakdown):")
    print("=" * 90)
    all_reasons = defaultdict(int)
    tp1_count = 0
    tp2_count = 0
    tp3_count = 0
    sl_count = 0
    trail_count = 0
    reversal_count = 0
    for t in trades:
        er_list = t.get("exit_reasons") or []
        for er in er_list:
            reason = er.get("reason", "unknown")
            all_reasons[reason] += 1
        # Per-trade: mark if any TP1/TP2 was hit
        reasons_set = {er.get("reason", "") for er in er_list}
        if "tp1" in reasons_set:
            tp1_count += 1
        if "tp2" in reasons_set:
            tp2_count += 1
        if "tp3" in reasons_set or "trailing_exit" in reasons_set:
            trail_count += 1
        if "stop_loss" in reasons_set:
            sl_count += 1
        if "signal_reversal" in reasons_set:
            reversal_count += 1
    print(f"  Partial close events (all):")
    for reason, count in sorted(all_reasons.items(), key=lambda x: -x[1]):
        print(f"    {reason:20s}: {count}")
    print(f"\n  Trades with at least one partial at each level:")
    print(f"    TP1 hit:              {tp1_count} ({tp1_count/len(trades)*100:.1f}%)")
    print(f"    TP2 hit:              {tp2_count} ({tp2_count/len(trades)*100:.1f}%)")
    print(f"    Trailing/TP3:         {trail_count} ({trail_count/len(trades)*100:.1f}%)")
    print(f"    Stop loss:            {sl_count} ({sl_count/len(trades)*100:.1f}%)")
    print(f"    Signal reversal:      {reversal_count} ({reversal_count/len(trades)*100:.1f}%)")
    total_partials = sum(all_reasons.values())
    print(f"\n  Total partial-close events: {total_partials}")
    print(f"  Avg partials per trade:    {total_partials/len(trades):.2f}")
    
    # --- P&L SUMMARY ---
    total_pnl = sum(t.get("realized_pnl_net", 0) for t in trades)
    winners = [t for t in trades if t.get("realized_pnl_net", 0) > 0]
    losers = [t for t in trades if t.get("realized_pnl_net", 0) <= 0]
    
    print("\n" + "=" * 90)
    print("P&L SUMMARY:")
    print("=" * 90)
    print(f"  Total PnL (net, from exchange): ${total_pnl:,.2f}")
    print(f"  Winning trades: {len(winners)} ({len(winners)/len(trades)*100:.1f}%)")
    print(f"  Losing trades:  {len(losers)} ({len(losers)/len(trades)*100:.1f}%)")
    
    if winners:
        avg_win = sum(t.get("realized_pnl_net", 0) for t in winners) / len(winners)
        max_win = max(t.get("realized_pnl_net", 0) for t in winners)
        sum_win = sum(t.get("realized_pnl_net", 0) for t in winners)
        print(f"  Gross wins:     +${sum_win:,.2f} | Avg: +${avg_win:,.2f} | Max: +${max_win:,.2f}")
    if losers:
        avg_loss = sum(t.get("realized_pnl_net", 0) for t in losers) / len(losers)
        max_loss = min(t.get("realized_pnl_net", 0) for t in losers)
        sum_loss = sum(t.get("realized_pnl_net", 0) for t in losers)
        print(f"  Gross losses:   ${sum_loss:,.2f} | Avg: ${avg_loss:,.2f} | Max: ${max_loss:,.2f}")
    
    # Profit factor
    gross_profit = sum(t.get("realized_pnl_net", 0) for t in winners) if winners else 0
    gross_loss = abs(sum(t.get("realized_pnl_net", 0) for t in losers)) if losers else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    print(f"\n  Profit Factor: {profit_factor:.2f}  (gross_profit/gross_loss)")
    
    # --- COMMISSIONS BREAKDOWN ---
    print("\n" + "=" * 90)
    print("COMMISSIONS & COSTS BREAKDOWN:")
    print("=" * 90)
    total_entry_fees = sum(t.get("entry_fees_est", 0) for t in trades)
    total_exit_fees = sum(t.get("exit_fees_est", 0) for t in trades)
    total_funding = sum(t.get("funding_estimate", 0) for t in trades)
    total_fees = total_entry_fees + total_exit_fees
    total_notional = sum(t.get("notional_entry", 0) for t in trades)
    
    print(f"  Total entry fees (est): ${total_entry_fees:,.2f}")
    print(f"  Total exit fees (est):  ${total_exit_fees:,.2f}")
    print(f"  Total fees (est):       ${total_fees:,.2f}")
    print(f"  Total funding (est):    ${total_funding:+,.2f}")
    print(f"  Total costs:            ${total_fees + total_funding:,.2f}")
    print(f"  Total notional traded:  ${total_notional:,.2f}")
    if total_notional > 0:
        print(f"  Fees as % of notional:  {total_fees/total_notional*100:.3f}%")
    
    # Gross (before fees) vs net
    # realized_pnl_net already includes fees from exchange
    # Gross PnL = net + fees (approximation)
    gross_pnl_est = total_pnl + total_fees + total_funding
    print(f"\n  Estimated gross PnL (before costs): ${gross_pnl_est:,.2f}")
    print(f"  Costs eaten PnL (fees+funding):     ${total_fees + total_funding:,.2f}")
    if gross_pnl_est != 0:
        cost_ratio = (total_fees + total_funding) / abs(gross_pnl_est) * 100
        print(f"  Costs as % of gross PnL:            {cost_ratio:.1f}%")
    
    # --- DIAGNOSIS ---
    print("\n" + "=" * 90)
    print("DIAGNOSIS: WHY IN MINUS?")
    print("=" * 90)
    wr = len(winners) / len(trades) * 100 if trades else 0
    avg_win_amt = sum(t.get("realized_pnl_net", 0) for t in winners) / len(winners) if winners else 0
    avg_loss_amt = abs(sum(t.get("realized_pnl_net", 0) for t in losers) / len(losers)) if losers else 0
    rr_actual = avg_win_amt / avg_loss_amt if avg_loss_amt > 0 else 0
    # Breakeven WR formula: WR_be = 1 / (1 + R:R)
    be_wr = 100 / (1 + rr_actual) if rr_actual > 0 else 0
    
    print(f"  Actual Win Rate:           {wr:.1f}%")
    print(f"  Actual R:R (avg_win/avg_loss): 1:{rr_actual:.2f}")
    print(f"  Breakeven Win Rate needed: {be_wr:.1f}%")
    print(f"  WR gap:                    {wr - be_wr:+.1f}% (negative = losing money)")
    
    print(f"\n  Root cause analysis:")
    if total_pnl < 0:
        if wr < 40:
            print(f"  ❌ LOW WIN RATE ({wr:.1f}%) — model accuracy issue")
        if rr_actual < 1.3:
            print(f"  ❌ POOR R:R ({rr_actual:.2f}) — TP/SL levels bad, exiting early or SL too wide")
        if total_fees > abs(total_pnl) * 0.3:
            print(f"  ❌ HIGH FEE BURDEN: fees ${total_fees:.2f} vs |PnL| ${abs(total_pnl):.2f}")
        if total_funding < -abs(total_pnl) * 0.1:
            print(f"  ❌ FUNDING DRAG: ${total_funding:.2f} significant")
        if wr >= 45 and rr_actual >= 1.3 and total_fees < abs(total_pnl) * 0.2:
            print(f"  ⚠️  Stats look OK but losing — check slippage and signal quality")
    else:
        print(f"  ✅ PROFITABLE")
    
    # Expectancy
    expectancy = total_pnl / len(trades) if trades else 0
    print(f"\n📊 EXPECTANCY: ${expectancy:.2f} per trade")
    
    # By symbol - detailed
    print("\n" + "=" * 90)
    print("PER-SYMBOL STATISTICS:")
    print("=" * 90)
    print(f"  {'SYMBOL':12} {'TRADES':>6} {'WR%':>5} {'PnL_NET':>10} {'FEES':>8} {'FUND':>7} "
          f"{'GROSS':>10} {'AVG_DUR':>8}")
    print("  " + "-" * 80)
    by_symbol = defaultdict(list)
    for t in trades:
        sym = t.get("symbol", "unknown")
        by_symbol[sym].append(t)
    for sym, group in sorted(by_symbol.items(), key=lambda x: sum(t.get("realized_pnl_net", 0) for t in x[1]), reverse=True):
        wins = len([t for t in group if t.get("realized_pnl_net", 0) > 0])
        pnl = sum(t.get("realized_pnl_net", 0) for t in group)
        fees_sym = sum(t.get("entry_fees_est", 0) + t.get("exit_fees_est", 0) for t in group)
        fund_sym = sum(t.get("funding_estimate", 0) for t in group)
        gross_sym = pnl + fees_sym + fund_sym
        avg_dur = sum(t.get("duration_sec", 0) for t in group) / len(group) if group else 0
        print(f"  {sym:12s} {len(group):6d} {wins/len(group)*100:5.1f} {pnl:+10.2f} "
              f"{fees_sym:8.2f} {fund_sym:+7.2f} {gross_sym:+10.2f} {int(avg_dur/60):6d}m")

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
    
    # EV Model Correlation Analysis
    print("\n🔬 EV MODEL CORRELATION:")
    ev_trades = [t for t in trades if t.get("signal", {}).get("ev", 0) != 0]
    if len(ev_trades) >= 2:
        predicted_evs = [t.get("signal", {}).get("ev", 0) for t in ev_trades]
        realized_pnls = [t.get("realized_pnl_net", 0) for t in ev_trades]
        
        # Calculate correlation
        try:
            corr = correlation(predicted_evs, realized_pnls)
            print(f"  Correlation(predicted_ev, realized_pnl): {corr:.3f}")
            if corr < -0.1:
                print(f"  ⚠️  NEGATIVE CORRELATION - EV model may be inverted!")
            elif corr < 0.1:
                print(f"  ⚠️  NO CORRELATION - EV model not predictive")
            else:
                print(f"  ✅ POSITIVE CORRELATION - EV model working as expected")
        except Exception as e:
            print(f"  Could not calculate correlation: {e}")
    else:
        print(f"  Not enough trades with EV data (need >=2, have {len(ev_trades)})")
    
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
    split_ts = None
    if len(sys.argv) > 2:
        # Accept split timestamp as either unix ts or "YYYY-MM-DD HH:MM:SS"
        arg = sys.argv[2]
        try:
            split_ts = float(arg)
        except ValueError:
            split_ts = datetime.strptime(arg, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()

    trades = load_trades(path)
    if split_ts:
        before = [t for t in trades if t.get("opened_ts", 0) < split_ts]
        after = [t for t in trades if t.get("opened_ts", 0) >= split_ts]
        print("\n" + "#" * 90)
        print(f"#  BEFORE SPLIT ({datetime.fromtimestamp(split_ts, tz=timezone.utc).isoformat()[:19]}Z)")
        print("#" * 90)
        analyze_trades(before, verbose=False)
        print("\n" + "#" * 90)
        print(f"#  AFTER SPLIT")
        print("#" * 90)
        analyze_trades(after, verbose=False)
    else:
        analyze_trades(trades)
