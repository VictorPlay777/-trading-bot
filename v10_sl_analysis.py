import json

trades = [json.loads(l) for l in open('logs/v10/trades_v10.jsonl')]
aero = [t for t in trades if t.get('symbol') == 'AEROUSDT']

print("=== AEROUSDT: What if SL was wider? ===\n")

for i, t in enumerate(aero, 1):
    entry = t['entry_price']
    exit_p = t.get('exit_price', 0)
    mfe = t.get('mfe_r', 0)
    mae = t.get('mae_r', 0)
    pnl = t.get('realized_pnl_net', 0)
    atr = t.get('signal', {}).get('atr', 0)
    
    # For short: SL = entry + 0.5*ATR
    sl_05 = entry + 0.5 * atr
    sl_10 = entry + 1.0 * atr  # wider SL
    sl_15 = entry + 1.5 * atr  # even wider
    
    # Price went against us by mae_r
    # If mae_r < -1.0, then even 1.0 ATR SL would be hit
    print(f"Trade #{i}: entry={entry:.4f}")
    print(f"  SL(0.5 ATR)={sl_05:.4f} | SL(1.0 ATR)={sl_10:.4f} | SL(1.5 ATR)={sl_15:.4f}")
    print(f"  Actual exit={exit_p:.4f} | PnL=${pnl:.0f}")
    print(f"  Max adverse move: {mae:.2f}R (if > -1.0, even 1.0 ATR SL gets hit)")
    print(f"  Max favorable: {mfe:.2f}R (if > +0.5, TP would trigger)")
    
    # Would wider SL help?
    if mae < -1.0:
        print(f"  → Wider SL to 1.0 ATR: STILL HIT (MAE was {mae:.2f}R)")
    elif mae < -0.5:
        print(f"  → Wider SL to 1.0 ATR: SURVIVES (MAE was {mae:.2f}R)")
    
    print()

# Summary
print("=== SUMMARY ===")
all_mae = [t.get('mae_r', 0) for t in aero]
all_mfe = [t.get('mfe_r', 0) for t in aero]
print(f"MAE range: {min(all_mae):.2f}R to {max(all_mae):.2f}R")
print(f"MFE range: {min(all_mfe):.2f}R to {max(all_mfe):.2f}R")
print(f"Trades that hit SL even at 1.0 ATR: {sum(1 for m in all_mae if m < -1.0)}/6")
print(f"Trades that would survive 1.0 ATR SL: {sum(1 for m in all_mae if m >= -1.0)}/6")
print(f"Trades that ever reached +0.5R MFE (would hit TP): {sum(1 for m in all_mfe if m >= 0.5)}/6")
