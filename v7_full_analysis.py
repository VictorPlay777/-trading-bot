#!/usr/bin/env python3
"""V7 Full Stats Analysis. Run from ~/v7_clean/."""
import csv, json, sys
from collections import defaultdict, Counter
from pathlib import Path

LOG_DIR = Path("logs")
OUT = LOG_DIR / "v7_analysis_report.txt"
_buf = []

def out(m=""):
    print(m); _buf.append(m)

def sec(t):
    out(); out("=" * 78); out(f"  {t}"); out("=" * 78)

def f(x, d=0.0):
    try: return float(x)
    except: return d

def m(x): return f"{x:+,.2f}"
def p(x): return f"{x*100:.1f}%"

def load_csv(path):
    if not path.exists(): return []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return list(csv.DictReader(fh))

def load_json(path):
    if not path.exists(): return {}
    try:
        return json.load(open(path, "r", encoding="utf-8"))
    except Exception as e:
        out(f"[WARN] {path}: {e}"); return {}

def get_pnl(t):
    for k in ("pnl", "realized_pnl", "net_pnl", "pnl_usd"):
        if k in t and t[k] not in ("", None):
            return f(t[k])
    return 0.0

def overall(trades):
    sec("OVERALL")
    if not trades:
        out("No trades."); return
    pnls = [get_pnl(t) for t in trades]
    n = len(pnls)
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x < 0]
    total = sum(pnls)
    wr = len(wins)/n if n else 0
    aw = sum(wins)/len(wins) if wins else 0
    al = sum(losses)/len(losses) if losses else 0
    pf = sum(wins)/abs(sum(losses)) if losses else float("inf")
    # drawdown
    run, peak, mdd = 0, 0, 0
    for x in pnls:
        run += x
        peak = max(peak, run)
        mdd = max(mdd, peak - run)
    out(f"Trades:        {n}")
    out(f"Wins/Losses:   {len(wins)}/{len(losses)}")
    out(f"Winrate:       {p(wr)}")
    out(f"Total PnL:     {m(total)} USDT")
    out(f"Expectancy:    {m(total/n if n else 0)} per trade")
    out(f"Avg win/loss:  {m(aw)} / {m(al)}")
    out(f"R:R:           {(aw/abs(al) if al else 0):.2f}")
    out(f"Profit factor: {pf:.2f}")
    out(f"Best/Worst:    {m(max(pnls))} / {m(min(pnls))}")
    out(f"Max DD:        -{mdd:,.2f}")
    # streaks
    cur, sign, mws, mls = 0, 0, 0, 0
    for x in pnls:
        s = 1 if x > 0 else (-1 if x < 0 else 0)
        if s == 0: continue
        cur = cur + 1 if s == sign else 1
        sign = s
        if s > 0: mws = max(mws, cur)
        else: mls = max(mls, cur)
    out(f"Max W/L streak: {mws} / {mls}")

def by_field(trades, field, label, top=10):
    sec(f"BY {label.upper()}")
    g = defaultdict(list)
    for t in trades:
        v = t.get(field) or "<unk>"
        g[v].append(get_pnl(t))
    rows = []
    for k, ps in g.items():
        n = len(ps); s = sum(ps)
        w = sum(1 for x in ps if x > 0)
        rows.append((k, n, w/n if n else 0, s, s/n if n else 0))
    rows.sort(key=lambda r: -r[3])
    out(f"{'KEY':<22} {'N':>5} {'WIN%':>7} {'TOTAL':>14} {'AVG':>10}")
    out("-" * 62)
    show = rows if len(rows) <= top*2 else rows[:top] + [("...", 0, 0, 0, 0)] + rows[-top:]
    for k, n, wr, s, a in show:
        if k == "...": out("..."); continue
        out(f"{str(k):<22} {n:>5} {p(wr):>7} {m(s):>14} {m(a):>10}")

def exit_reasons(trades):
    sec("EXIT REASONS")
    c = Counter(); pnl = defaultdict(float)
    for t in trades:
        r = t.get("exit_reason") or t.get("reason") or "<unk>"
        c[r] += 1; pnl[r] += get_pnl(t)
    out(f"{'REASON':<22} {'N':>5} {'TOTAL':>14}")
    for r, n in c.most_common():
        out(f"{r:<22} {n:>5} {m(pnl[r]):>14}")

def signals_funnel(sigs):
    sec("SIGNAL FUNNEL")
    if not sigs:
        out("No signals."); return
    n = len(sigs)
    a = sum(1 for s in sigs if str(s.get("allow", "")).lower() == "true")
    out(f"Total: {n}, Allowed: {a} ({p(a/n)}), Rejected: {n-a}")
    rc = Counter()
    for s in sigs:
        if str(s.get("allow", "")).lower() != "true":
            rc[s.get("reason", "<unk>")] += 1
    out("\nTop reject reasons:")
    for r, c2 in rc.most_common(15):
        out(f"  {r:<45} {c2:>6}")

def conf_buckets(d):
    sec("CONFIDENCE BUCKETS")
    if not d:
        out("Missing."); return
    rows = []
    for b, v in d.items():
        n = v.get("trades", 0)
        rows.append((b, n, v.get("winrate", 0), v.get("avg_pnl", 0),
                     v.get("pnl_sum", v.get("avg_pnl", 0) * n)))
    def k(r):
        try: return float(r[0].split("-")[0].replace("<","").replace("+",""))
        except: return 0
    rows.sort(key=k)
    out(f"{'BUCKET':<12} {'N':>5} {'WIN%':>7} {'AVG':>10} {'TOTAL':>14}")
    for b, n, wr, a, t in rows:
        out(f"{b:<12} {n:>5} {p(wr):>7} {m(a):>10} {m(t):>14}")
    # correlation
    pts = [(k((b,)), v) for b, n, wr, a, v in [(r[0], r[1], r[2], r[3], r[3]) for r in rows]]
    xs = [k((b,)) for b, *_ in rows]
    ys = [r[3] for r in rows]
    if len(xs) > 1:
        mx, my = sum(xs)/len(xs), sum(ys)/len(ys)
        num = sum((a-mx)*(b-my) for a, b in zip(xs, ys))
        dx = (sum((a-mx)**2 for a in xs))**0.5
        dy = (sum((b-my)**2 for b in ys))**0.5
        corr = num/(dx*dy) if dx and dy else 0
        out(f"\nCorr(confidence, avg_pnl) = {corr:+.3f}")
        if corr > 0.3: out(">>> EDGE: higher conf -> more profit")
        elif corr < -0.3: out(">>> INVERSION: higher conf -> more LOSS. Consider fading.")
        else: out(">>> NO RELATIONSHIP: model has no edge.")

def by_symbol(d, top=15):
    sec(f"BY SYMBOL (top/bottom {top})")
    if not d:
        out("Missing."); return
    rows = []
    for s, v in d.items():
        n = v.get("total_trades", v.get("trades", 0))
        a = v.get("avg_pnl", 0)
        rows.append((s, n, v.get("winrate", 0), a, v.get("pnl_sum", a*n)))
    rows.sort(key=lambda r: -r[4])
    out(f"{'SYM':<16} {'N':>5} {'WIN%':>7} {'AVG':>10} {'TOTAL':>14}")
    out(f"--- TOP {top} ---")
    for s, n, wr, a, t in rows[:top]:
        out(f"{s:<16} {n:>5} {p(wr):>7} {m(a):>10} {m(t):>14}")
    out(f"--- BOTTOM {top} ---")
    for s, n, wr, a, t in rows[-top:]:
        out(f"{s:<16} {n:>5} {p(wr):>7} {m(a):>10} {m(t):>14}")

def main():
    out(f"V7 Analysis Report  | cwd={Path.cwd()}")
    trades = load_csv(LOG_DIR / "trade_log.csv")
    sigs = load_csv(LOG_DIR / "signal_log.csv")
    sc = load_json(LOG_DIR / "stats_by_confidence.json")
    ss = load_json(LOG_DIR / "stats_by_symbol.json")

    out(f"trades.csv: {len(trades)} rows")
    out(f"signals.csv: {len(sigs)} rows")
    if trades:
        out(f"trade fields: {list(trades[0].keys())}")
    if sigs:
        out(f"signal fields: {list(sigs[0].keys())}")

    overall(trades)
    if trades:
        # detect available fields
        fields = trades[0].keys()
        if "side" in fields: by_field(trades, "side", "side")
        if "regime" in fields: by_field(trades, "regime", "regime")
        if "symbol" in fields: by_field(trades, "symbol", "symbol", top=10)
        exit_reasons(trades)

    signals_funnel(sigs)
    conf_buckets(sc)
    by_symbol(ss)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(_buf))
    out(f"\n[SAVED] {OUT}")

if __name__ == "__main__":
    main()
