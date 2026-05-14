#!/usr/bin/env python3
"""Backtest different exit strategies on real V10 trades (scalar MFE/MAE only)."""
import json

TRADES = "/home/svy1990/-trading-bot/logs/v10/trades_v10.jsonl"

def load_trades():
    out = []
    with open(TRADES) as f:
        for line in f:
            try:
                t = json.loads(line.strip())
                if t.get("mfe_r") is not None and t.get("mae_r") is not None and t.get("exit_r") is not None:
                    out.append(t)
            except: pass
    return out

def simulate_exit(mfe, mae, actual_exit, sl_r, tp_r, be_arm_r=None, be_offset_r=0.05):
    """
    Conservative scalar simulation.
    Assumption: if BOTH SL and TP could be hit (|mae|>=sl_r AND mfe>=tp_r),
    we assume SL hit FIRST (worst case).
    BE-stop: if mfe >= be_arm_r, and actual_exit < be_offset_r, exit at be_offset_r.
    """
    # Check BE-stop
    if be_arm_r and mfe >= be_arm_r and actual_exit < be_offset_r:
        return be_offset_r
    
    # Check if TP was reached
    tp_reached = mfe >= tp_r
    # Check if SL was reached
    sl_reached = abs(mae) >= sl_r
    
    if tp_reached and sl_reached:
        # CONSERVATIVE: assume SL hit first
        return -sl_r
    elif tp_reached:
        return tp_r
    elif sl_reached:
        return -sl_r
    else:
        # Neither hit — use actual exit
        return actual_exit

def backtest(trades, name, sl_r, tp_r, be_arm_r=None, be_offset_r=0.05):
    results = []
    for t in trades:
        er = simulate_exit(
            float(t.get("mfe_r", 0)),
            float(t.get("mae_r", 0)),
            float(t.get("exit_r", 0)),
            sl_r, tp_r, be_arm_r, be_offset_r
        )
        results.append(er)
    
    n = len(results)
    wins = sum(1 for r in results if r > 0)
    losses = sum(1 for r in results if r < 0)
    be_count = sum(1 for r in results if r == 0)
    total_r = sum(results)
    avg_r = total_r / n
    wr = wins / n * 100 if n else 0
    
    # Convert to dollars
    total_dollars = 0.0
    for t, r in zip(trades, results):
        notional = float(t.get("notional_entry", 10000) or 10000)
        entry = float(t.get("entry_price", 0) or 0)
        atr = float(t.get("signal", {}).get("atr", 0) or 0)
        if entry > 0 and atr > 0:
            dollars = r * 0.5 * (atr / entry) * notional
            total_dollars += dollars
    
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    print(f"  SL={sl_r}R  TP={tp_r}R  BE@={be_arm_r}R  offset={be_offset_r}R")
    print(f"  Trades: {n}  |  WR: {wr:.1f}% ({wins}W / {losses}L / {be_count}BE)")
    print(f"  Total R: {total_r:+.2f}  |  Avg R/trade: {avg_r:+.3f}")
    print(f"  Total $: ${total_dollars:+,.2f}")
    return total_r, total_dollars

def main():
    trades = load_trades()
    print(f"Loaded {len(trades)} trades with MFE/MAE/exit_r")
    
    print("\n" + "="*60)
    print("EXIT STRATEGY BACKTEST (Conservative: SL-first on conflicts)")
    print("="*60)
    
    strategies = [
        ("1. BASELINE (SL=1R, TP=1R)", 1.0, 1.0, None),
        ("2. BE-STOP @ 0.3R", 1.0, 1.0, 0.3),
        ("3. BE-STOP @ 0.5R", 1.0, 1.0, 0.5),
        ("4. WIDER SL (SL=1.5R, TP=1R)", 1.5, 1.0, None),
        ("5. WIDER TP (SL=1R, TP=1.5R)", 1.0, 1.5, None),
        ("6. ASYMMETRIC (SL=1R, TP=1.5R, BE@0.5R)", 1.0, 1.5, 0.5),
        ("7. AGGRESSIVE TP (SL=1R, TP=2R, BE@0.5R)", 1.0, 2.0, 0.5),
        ("8. WIDE SL+TP (SL=2R, TP=2R, BE@0.5R)", 2.0, 2.0, 0.5),
        ("9. TIGHT SL (SL=0.5R, TP=1R)", 0.5, 1.0, None),
        ("10. BE@0.5R + TP=2R (R:R=2:1)", 1.0, 2.0, 0.5),
        ("11. NO TP (SL=1.5R, BE@0.5R)", 1.5, 999.0, 0.5),
    ]
    
    best_r = -999
    best_name = ""
    for name, sl, tp, be in strategies:
        tr, td = backtest(trades, name, sl, tp, be)
        if tr > best_r:
            best_r = tr
            best_name = name
    
    print(f"\n{'='*60}")
    print(f"BEST STRATEGY: {best_name}")
    print(f"Total R: {best_r:+.2f}")
    print(f"{'='*60}")
    
    print("\n--- MFE/MAE DISTRIBUTION ---")
    mfes = [t["mfe_r"] for t in trades]
    maes = [abs(t["mae_r"]) for t in trades]
    print(f"  MFE >= 0.5R: {sum(1 for m in mfes if m>=0.5)/len(mfes)*100:.1f}%")
    print(f"  MFE >= 1.0R: {sum(1 for m in mfes if m>=1.0)/len(mfes)*100:.1f}%")
    print(f"  MFE >= 1.5R: {sum(1 for m in mfes if m>=1.5)/len(mfes)*100:.1f}%")
    print(f"  MFE >= 2.0R: {sum(1 for m in mfes if m>=2.0)/len(mfes)*100:.1f}%")
    print(f"  |MAE| >= 0.5R: {sum(1 for m in maes if m>=0.5)/len(maes)*100:.1f}%")
    print(f"  |MAE| >= 1.0R: {sum(1 for m in maes if m>=1.0)/len(maes)*100:.1f}%")
    print(f"  |MAE| >= 1.5R: {sum(1 for m in maes if m>=1.5)/len(maes)*100:.1f}%")

if __name__ == "__main__":
    main()
