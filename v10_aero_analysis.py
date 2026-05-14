import json
from collections import defaultdict

# Load all trades
trades = [json.loads(l) for l in open('logs/v10/trades_v10.jsonl')]

# Filter AEROUSDT
aero_trades = [t for t in trades if t.get('symbol') == 'AEROUSDT']

print(f"=== AEROUSDT DEEP DIVE ({len(aero_trades)} trades) ===\n")

# Basic stats
wins = sum(1 for t in aero_trades if t.get('realized_pnl_net', 0) > 0)
pnl = sum(t.get('realized_pnl_net', 0) for t in aero_trades)
print(f"Total trades: {len(aero_trades)}")
print(f"Wins/Losses: {wins}/{len(aero_trades)-wins}")
print(f"Winrate: {wins/len(aero_trades)*100:.1f}%")
print(f"Total PnL: ${pnl:.2f}")
print(f"Avg PnL per trade: ${pnl/len(aero_trades):.2f}")

# Per-trade breakdown
print("\n=== PER-TRADE BREAKDOWN ===")
print(f"{'#':<3} {'Dir':<5} {'Conf':<6} {'Regime':<6} {'ADX':<5} {'Entry':<10} {'Exit':<10} {'PnL':<10} {'ExitReason':<12} {'MFE_R':<6} {'MAE_R':<6}")
for i, t in enumerate(aero_trades, 1):
    sig = t.get('signal', {})
    direction = t.get('direction', '?')
    conf = sig.get('confidence', 0)
    regime = sig.get('regime', '?')
    adx = sig.get('adx', 0)
    entry = t.get('entry_price', 0)
    exit_p = t.get('exit_price', 0)
    pnl_t = t.get('realized_pnl_net', 0)
    reason = t.get('exit_reasons', [{}])[0].get('reason', '?')
    mfe = t.get('mfe_r', 0)
    mae = t.get('mae_r', 0)
    
    print(f"{i:<3} {direction:<5} {conf:<6.3f} {regime:<6} {adx:<5.1f} {entry:<10.4f} {exit_p:<10.4f} {pnl_t:<10.2f} {reason:<12} {mfe:<6.2f} {mae:<6.2f}")

# Analyze patterns
print("\n=== PATTERN ANALYSIS ===")

# By direction
longs = [t for t in aero_trades if t.get('direction') == 'long']
shorts = [t for t in aero_trades if t.get('direction') == 'short']
print(f"Longs: {len(longs)} trades, WR={sum(1 for t in longs if t.get('realized_pnl_net',0)>0)/max(1,len(longs))*100:.0f}%")
print(f"Shorts: {len(shorts)} trades, WR={sum(1 for t in shorts if t.get('realized_pnl_net',0)>0)/max(1,len(shorts))*100:.0f}%")

# By regime
for r in ['chop', 'trend']:
    subset = [t for t in aero_trades if t.get('signal',{}).get('regime') == r]
    if subset:
        wr = sum(1 for t in subset if t.get('realized_pnl_net',0)>0) / len(subset) * 100
        avg_pnl = sum(t.get('realized_pnl_net',0) for t in subset) / len(subset)
        print(f"Regime {r}: {len(subset)} trades, WR={wr:.0f}%, avg PnL=${avg_pnl:.2f}")

# Confidence pattern
avg_conf = sum(t.get('signal',{}).get('confidence',0) for t in aero_trades) / len(aero_trades)
print(f"\nAvg confidence: {avg_conf:.3f}")

# Compare to other symbols
print("\n=== COMPARISON: AERO vs ALL OTHERS ===")
other_trades = [t for t in trades if t.get('symbol') != 'AEROUSDT']
other_wins = sum(1 for t in other_trades if t.get('realized_pnl_net', 0) > 0)
other_pnl = sum(t.get('realized_pnl_net', 0) for t in other_trades)
print(f"All others: {len(other_trades)} trades, WR={other_wins/len(other_trades)*100:.1f}%, PnL=${other_pnl:.2f}")
print(f"AEROUSDT: {len(aero_trades)} trades, WR={wins/len(aero_trades)*100:.1f}%, PnL=${pnl:.2f}")

# Shadow trades for AERO
print("\n=== SHADOW TRADES FOR AEROUSDT ===")
try:
    shadows = [json.loads(l) for l in open('logs/v10/shadow_trades.jsonl')]
    aero_shadows = [s for s in shadows if s.get('symbol') == 'AEROUSDT']
    if aero_shadows:
        shadow_wins = sum(1 for s in aero_shadows if s.get('virtual_exit_r', -999) > 0)
        print(f"Shadow trades: {len(aero_shadows)}, WR={shadow_wins/len(aero_shadows)*100:.1f}%")
    else:
        print("No shadow trades for AEROUSDT")
except:
    print("Could not load shadow trades")
