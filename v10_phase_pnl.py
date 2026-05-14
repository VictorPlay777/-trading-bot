"""Match trades to signals by symbol+timestamp proximity and report PnL by market_phase."""
import json
import bisect
from collections import defaultdict

SIGNALS = "/home/svy1990/-trading-bot/logs/v10/signals_all.jsonl"
TRADES = "/home/svy1990/-trading-bot/logs/v10/trades_v10.jsonl"

by_sym = defaultdict(list)
with open(SIGNALS) as f:
    for line in f:
        try:
            s = json.loads(line)
            if not s.get("allow"):
                continue
            extra = s.get("extra") or {}
            phase = extra.get("market_phase")
            if not phase:
                continue
            sym = s.get("symbol", "")
            ts = s.get("timestamp", 0) or s.get("ts", 0)
            side = s.get("side", "?")
            by_sym[sym].append((int(ts), phase, side))
        except Exception:
            pass

for sym in by_sym:
    by_sym[sym].sort(key=lambda x: x[0])

def find_phase(sym, ts, trade_side, window=300):
    arr = by_sym.get(sym, [])
    if not arr:
        return "", ""
    idx = bisect.bisect_left([x[0] for x in arr], ts)
    best = ""
    best_side = ""
    best_dt = window + 1
    for i in [idx - 1, idx, idx + 1]:
        if 0 <= i < len(arr):
            dt = abs(arr[i][0] - ts)
            if dt < best_dt:
                best_dt = dt
                best = arr[i][1]
                best_side = arr[i][2]
    if best_side and best_side != trade_side:
        for i in range(max(0, idx-3), min(len(arr), idx+4)):
            if arr[i][2] == trade_side:
                dt = abs(arr[i][0] - ts)
                if dt <= window:
                    return arr[i][1], arr[i][2]
        return "", ""
    return best, best_side

trades = []
with open(TRADES) as f:
    for line in f:
        try:
            t = json.loads(line)
            sym = t.get("symbol", "")
            ts = int(t.get("opened_ts", 0) or t.get("timestamp", 0) or 0)
            side = t.get("side") or t.get("direction") or "?"
            phase, sig_side = find_phase(sym, ts, side, window=300)
            t["_market_phase"] = phase
            trades.append(t)
        except Exception:
            pass

by_phase = defaultdict(list)
for t in trades:
    ph = t.get("_market_phase")
    if ph:
        by_phase[ph].append(t)

by_phase_side = defaultdict(lambda: defaultdict(list))
for t in trades:
    ph = t.get("_market_phase")
    if ph:
        side = t.get("side") or t.get("direction") or "?"
        by_phase_side[ph][side].append(t)

print("=" * 65)
print("PnL BY MARKET PHASE (v2: symbol+timestamp proximity, 5min window)")
print("=" * 65)
print(f"Matched: {sum(len(v) for v in by_phase.values())}/{len(trades)}")

for phase in sorted(by_phase.keys()):
    rows = by_phase[phase]
    pnls = [float(t.get("realized_pnl_net", 0) or 0) for t in rows]
    wins = sum(1 for p in pnls if p > 0)
    total = sum(pnls)
    avg = total / max(1, len(pnls))
    wr = wins / max(1, len(pnls))
    print(f"\n{phase:16s}  n={len(pnls):4d}  W/L={wins}/{len(pnls)-wins}  WR={wr*100:.1f}%  Total=${total:,.2f}  Avg=${avg:,.2f}")
    for side in sorted(by_phase_side[phase].keys()):
        srows = by_phase_side[phase][side]
        spnls = [float(t.get("realized_pnl_net", 0) or 0) for t in srows]
        sw = sum(1 for p in spnls if p > 0)
        stotal = sum(spnls)
        savg = stotal / max(1, len(srows))
        is_anti = (phase, side) in {("pump","short"),("dump","long"),("dump_start","long"),("dump_bottom","long"),("bounce","short"),("uptrend","short"),("downtrend","long")}
        print(f"    -> {side:5s}  n={len(srows):4d}  W/L={sw}/{len(srows)-sw}  WR={sw/max(1,len(srows))*100:.1f}%  Total=${stotal:,.2f}  Avg=${savg:,.2f}{' [ANTI]' if is_anti else ''}")

anti = []
trend = []
for t in trades:
    ph = t.get("_market_phase")
    side = t.get("side") or t.get("direction") or "?"
    pnl = float(t.get("realized_pnl_net", 0) or 0)
    if (ph, side) in {("pump","short"),("dump","long"),("dump_start","long"),("dump_bottom","long"),("bounce","short"),("uptrend","short"),("downtrend","long")}:
        anti.append(pnl)
    elif (ph, side) in {("pump","long"),("dump","short"),("dump_start","short"),("uptrend","long"),("downtrend","short")}:
        trend.append(pnl)

print("\n" + "=" * 65)
print("ANTI-TREND vs TREND-FOLLOWING")
print("=" * 65)
if anti:
    w = sum(1 for p in anti if p > 0)
    print(f"Anti-trend:   n={len(anti):3d}  W/L={w}/{len(anti)-w}  WR={w/len(anti)*100:.1f}%  Total=${sum(anti):,.2f}  Avg=${sum(anti)/len(anti):,.2f}")
if trend:
    w = sum(1 for p in trend if p > 0)
    print(f"Trend-follow: n={len(trend):3d}  W/L={w}/{len(trend)-w}  WR={w/len(trend)*100:.1f}%  Total=${sum(trend):,.2f}  Avg=${sum(trend)/len(trend):,.2f}")

unmatched = [t for t in trades if not t.get("_market_phase")]
if unmatched:
    print(f"\nUnmatched trades: {len(unmatched)}")
    t = unmatched[0]
    print(f"Sample keys: {sorted(t.keys())[:15]}")
