import json
from collections import defaultdict

# Load trades
trades = [json.loads(l) for l in open('logs/v10/trades_v10.jsonl')]

print(f"=== CORRELATION ANALYSIS ({len(trades)} trades) ===\n")

# 1. EV vs PnL
print("=== EXPECTED VALUE (EV) vs OUTCOME ===")
ev_buckets = defaultdict(lambda: {'n': 0, 'wins': 0, 'pnl': 0, 'avg_conf': 0})
for t in trades:
    ev = t.get('signal', {}).get('ev', 0)
    pnl = t.get('realized_pnl_net', 0)
    conf = t.get('signal', {}).get('confidence', 0)
    
    if ev < 0:
        bucket = 'negative'
    elif ev < 0.01:
        bucket = '0-0.01'
    elif ev < 0.02:
        bucket = '0.01-0.02'
    else:
        bucket = '0.02+'
    
    b = ev_buckets[bucket]
    b['n'] += 1
    b['wins'] += 1 if pnl > 0 else 0
    b['pnl'] += pnl
    b['avg_conf'] += conf

for bucket in ['negative', '0-0.01', '0.01-0.02', '0.02+']:
    b = ev_buckets[bucket]
    if b['n'] > 0:
        wr = b['wins'] / b['n'] * 100
        avg_conf = b['avg_conf'] / b['n']
        print(f"  EV={bucket:10} | n={b['n']:2} | WR={wr:5.1f}% | PnL=${b['pnl']:8.2f} | avg_conf={avg_conf:.3f}")

# 2. ADX vs PnL
print("\n=== ADX vs OUTCOME ===")
adx_buckets = defaultdict(lambda: {'n': 0, 'wins': 0, 'pnl': 0})
for t in trades:
    adx = t.get('signal', {}).get('adx', 0)
    pnl = t.get('realized_pnl_net', 0)
    
    if adx < 30:
        bucket = 'weak(<30)'
    elif adx < 50:
        bucket = 'moderate(30-50)'
    elif adx < 70:
        bucket = 'strong(50-70)'
    else:
        bucket = 'very_strong(70+)'
    
    b = adx_buckets[bucket]
    b['n'] += 1
    b['wins'] += 1 if pnl > 0 else 0
    b['pnl'] += pnl

for bucket in ['weak(<30)', 'moderate(30-50)', 'strong(50-70)', 'very_strong(70+)']:
    b = adx_buckets[bucket]
    if b['n'] > 0:
        wr = b['wins'] / b['n'] * 100
        print(f"  ADX={bucket:20} | n={b['n']:2} | WR={wr:5.1f}% | PnL=${b['pnl']:8.2f}")

# 3. Combined: Regime + Confidence
print("\n=== REGIME + CONFIDENCE COMBINED ===")
combo = defaultdict(lambda: {'n': 0, 'wins': 0, 'pnl': 0})
for t in trades:
    regime = t.get('signal', {}).get('regime', 'unknown')
    conf = t.get('signal', {}).get('confidence', 0)
    pnl = t.get('realized_pnl_net', 0)
    
    if conf < 0.65:
        conf_bucket = 'low(<0.65)'
    elif conf < 0.80:
        conf_bucket = 'mid(0.65-0.80)'
    elif conf < 0.90:
        conf_bucket = 'high(0.80-0.90)'
    else:
        conf_bucket = 'very_high(0.90+)'
    
    key = f"{regime}+{conf_bucket}"
    b = combo[key]
    b['n'] += 1
    b['wins'] += 1 if pnl > 0 else 0
    b['pnl'] += pnl

for key in sorted(combo.keys()):
    b = combo[key]
    wr = b['wins'] / b['n'] * 100
    print(f"  {key:35} | n={b['n']:2} | WR={wr:5.1f}% | PnL=${b['pnl']:8.2f}")

# 4. EV vs Confidence correlation
print("\n=== EV vs CONFIDENCE CORRELATION ===")
print("(higher EV should correlate with higher confidence)")
ev_conf = []
for t in trades:
    ev = t.get('signal', {}).get('ev', 0)
    conf = t.get('signal', {}).get('confidence', 0)
    ev_conf.append((ev, conf))

if ev_conf:
    avg_ev_low_conf = sum(e for e,c in ev_conf if c < 0.70) / max(1, sum(1 for e,c in ev_conf if c < 0.70))
    avg_ev_high_conf = sum(e for e,c in ev_conf if c >= 0.85) / max(1, sum(1 for e,c in ev_conf if c >= 0.85))
    print(f"  avg EV for conf<0.70: {avg_ev_low_conf:.4f}")
    print(f"  avg EV for conf>=0.85: {avg_ev_high_conf:.4f}")

# 5. Per-symbol stats
print("\n=== BY SYMBOL (sorted by WR) ===")
sym_stats = defaultdict(lambda: {'n': 0, 'wins': 0, 'pnl': 0})
for t in trades:
    sym = t.get('symbol', 'unknown')
    pnl = t.get('realized_pnl_net', 0)
    s = sym_stats[sym]
    s['n'] += 1
    s['wins'] += 1 if pnl > 0 else 0
    s['pnl'] += pnl

# Sort by winrate
sorted_syms = sorted(sym_stats.items(), key=lambda x: x[1]['wins']/x[1]['n'] if x[1]['n']>0 else 0, reverse=True)
for sym, s in sorted_syms:
    if s['n'] >= 2:  # Only symbols with 2+ trades
        wr = s['wins'] / s['n'] * 100
        print(f"  {sym:15} | n={s['n']:2} | WR={wr:5.1f}% | PnL=${s['pnl']:8.2f}")

# Show 1-trade symbols
one_trade = [(sym, s) for sym, s in sym_stats.items() if s['n'] == 1]
if one_trade:
    print(f"\n  --- Single trade symbols ({len(one_trade)} total) ---")
    wins = sum(1 for sym,s in one_trade if s['pnl'] > 0)
    print(f"  Wins: {wins}/{len(one_trade)} ({wins/len(one_trade)*100:.1f}%)")
