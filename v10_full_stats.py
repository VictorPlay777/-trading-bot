"""V10 Full Statistical Analysis"""
import json
import bisect
from collections import defaultdict, Counter

SIGNALS = "/home/svy1990/-trading-bot/logs/v10/signals_all.jsonl"
TRADES = "/home/svy1990/-trading-bot/logs/v10/trades_v10.jsonl"

def median(vals):
    s = sorted(v for v in vals if v is not None)
    if not s: return 0.0
    n = len(s)
    return s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2

def mean(vals):
    s = [v for v in vals if v is not None]
    return sum(s)/len(s) if s else 0.0

by_sym = defaultdict(list)
with open(SIGNALS) as f:
    for line in f:
        try:
            s = json.loads(line)
            if not s.get("allow"): continue
            extra = s.get("extra") or {}
            phase = extra.get("market_phase")
            if not phase: continue
            ts = s.get("timestamp",0) or s.get("ts",0)
            by_sym[s.get("symbol","")].append((int(ts), phase, s.get("side","?")))
        except: pass

for sym in by_sym:
    by_sym[sym].sort(key=lambda x: x[0])

def find_phase(sym, ts, trade_side, window=300):
    arr = by_sym.get(sym, [])
    if not arr: return "", ""
    idx = bisect.bisect_left([x[0] for x in arr], ts)
    best, best_side, best_dt = "", "", window+1
    for i in [idx-1, idx, idx+1]:
        if 0 <= i < len(arr):
            dt = abs(arr[i][0]-ts)
            if dt < best_dt:
                best_dt, best, best_side = dt, arr[i][1], arr[i][2]
    if best_side and best_side != trade_side:
        for i in range(max(0,idx-3), min(len(arr),idx+4)):
            if arr[i][2] == trade_side:
                if abs(arr[i][0]-ts) <= window:
                    return arr[i][1], arr[i][2]
        return "", ""
    return best, best_side

trades = []
with open(TRADES) as f:
    for line in f:
        try:
            t = json.loads(line)
            sym = t.get("symbol","")
            ts = int(t.get("opened_ts",0) or t.get("timestamp",0) or 0)
            side = t.get("side") or t.get("direction") or "?"
            phase, _ = find_phase(sym, ts, side)
            t["_market_phase"] = phase
            trades.append(t)
        except: pass

pnls = [float(t.get("realized_pnl_net",0) or 0) for t in trades]
wins = [p for p in pnls if p > 0]
losses = [p for p in pnls if p <= 0]
wr = len(wins)/max(1,len(pnls))
avg_win = sum(wins)/max(1,len(wins))
avg_loss = sum(losses)/max(1,len(losses))
pf = abs(sum(wins)/sum(losses)) if losses else float('inf')
exp = sum(pnls)/max(1,len(pnls))

print("="*70)
print("V10 FULL STATISTICAL ANALYSIS")
print("="*70)
print(f"Total trades: {len(pnls)}")
print(f"Total PnL:    ${sum(pnls):,.2f}")
print(f"Winrate:      {wr*100:.1f}%")
print(f"Avg Win:      ${avg_win:,.2f}")
print(f"Avg Loss:     ${avg_loss:,.2f}")
print(f"Profit Factor: {pf:.2f}")
print(f"Expectancy:   ${exp:,.2f}")
print(f"Median PnL:   ${median(pnls):,.2f}")

mfe_vals = [float(t.get("mfe_r",0) or 0) for t in trades if t.get("mfe_r") is not None]
mae_vals = [float(t.get("mae_r",0) or 0) for t in trades if t.get("mae_r") is not None]
print("\n--- MFE / MAE ---")
if mfe_vals:
    print(f"Trades with MFE/MAE: {len(mfe_vals)}")
    print(f"Median MFE: {median(mfe_vals):.2f}R  Mean MFE: {mean(mfe_vals):.2f}R")
    print(f"MFE >= 0.5R: {sum(1 for v in mfe_vals if v>=0.5)/len(mfe_vals)*100:.1f}%")
    print(f"MFE >= 1.0R: {sum(1 for v in mfe_vals if v>=1.0)/len(mfe_vals)*100:.1f}%")
    print(f"MFE >= 2.0R: {sum(1 for v in mfe_vals if v>=2.0)/len(mfe_vals)*100:.1f}%")
if mae_vals:
    print(f"Median MAE: {median(mae_vals):.2f}R")
    print(f"MAE <= -1.0R: {sum(1 for v in mae_vals if v<=-1.0)/len(mae_vals)*100:.1f}%")

reasons = Counter()
for t in trades:
    ers = t.get("exit_reasons",[])
    if ers: reasons[ers[-1].get("reason","unknown")] += 1
print("\n--- EXIT REASONS ---")
for r,n in reasons.most_common():
    print(f"  {r:35s} {n:4d}  ({n/max(1,len(trades))*100:5.1f}%)")

by_phase = defaultdict(list)
for t in trades:
    ph = t.get("_market_phase")
    if ph: by_phase[ph].append(t)
print(f"\n--- PnL BY PHASE (matched {sum(len(v) for v in by_phase.values())}/{len(trades)}) ---")
for phase in sorted(by_phase.keys()):
    pp = [float(t.get("realized_pnl_net",0) or 0) for t in by_phase[phase]]
    w = sum(1 for p in pp if p > 0)
    print(f"  {phase:16s} n={len(pp):4d} W/L={w}/{len(pp)-w} WR={w/max(1,len(pp))*100:.1f}% Total=${sum(pp):,.2f}")

anti=[]; trend=[]
for t in trades:
    ph=t.get("_market_phase"); side=t.get("side") or t.get("direction") or "?"
    pnl=float(t.get("realized_pnl_net",0) or 0)
    if (ph,side) in {("pump","short"),("dump","long"),("dump_start","long"),("dump_bottom","long"),("bounce","short"),("uptrend","short"),("downtrend","long")}: anti.append(pnl)
    elif (ph,side) in {("pump","long"),("dump","short"),("dump_start","short"),("uptrend","long"),("downtrend","short")}: trend.append(pnl)
if anti:
    w=sum(1 for p in anti if p>0)
    print(f"\nAnti-trend:   n={len(anti)} WR={w/max(1,len(anti))*100:.1f}% Total=${sum(anti):,.2f}")
if trend:
    w=sum(1 for p in trend if p>0)
    print(f"Trend-follow: n={len(trend)} WR={w/max(1,len(trend))*100:.1f}% Total=${sum(trend):,.2f}")

durations = [float(t.get("duration_sec",0) or 0)/60 for t in trades if t.get("duration_sec")]
if durations:
    print(f"\n--- HOLD TIME ---")
    print(f"Median: {median(durations):.1f}min  Mean: {mean(durations):.1f}min")
    print(f"<5min: {sum(1 for d in durations if d<5)/len(durations)*100:.1f}%  5-30min: {sum(1 for d in durations if 5<=d<30)/len(durations)*100:.1f}%")

print("\n" + "="*70)
print("RECOMMENDATIONS")
print("="*70)
if mfe_vals:
    mfe50 = sum(1 for v in mfe_vals if v>=0.5)/len(mfe_vals)
    mfe100 = sum(1 for v in mfe_vals if v>=1.0)/len(mfe_vals)
    print(f"[MFE] {mfe50*100:.0f}% reach 0.5R, {mfe100*100:.0f}% reach 1.0R")
    print(f"  -> Current TP=0.5R underutilizes; TP=1.0R would capture {mfe100*100:.0f}% of max moves")
if wr < 0.45:
    print(f"[R:R] Winrate {wr*100:.1f}% < 50% -> bot loses at 1:1 R:R")
    print(f"  -> Need R:R >= 1.25:1 OR winrate >50%")
    print(f"  -> 55% hit SL, 45% hit TP1 -> adjust exits or entries")
if anti and trend:
    aw = sum(1 for p in anti if p>0)/max(1,len(anti))
    tw = sum(1 for p in trend if p>0)/max(1,len(trend))
    if aw > tw:
        print(f"[PHASE] Anti-trend WR={aw*100:.1f}% > Trend WR={tw*100:.1f}%")
        print(f"  -> Model catches mean-reversion; phase-gate may HURT")
    else:
        print(f"[PHASE] Trend-following is better; keep phase-gate")
print(f"[ACTION] 1. Move TP to 1.0-2.0R  2. Add BE-stop at 0.5R  3. Widen SL or tighten entries")
