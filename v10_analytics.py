"""
V10 Analytics CLI
=================
Post-hoc statistical analysis of v10 research outputs:
- logs/v10/trades_v10.jsonl  (real trades with MFE/MAE/feature_hash)
- logs/v10/shadow_trades.jsonl (virtual trades for rejected signals)
- logs/v10/signals_all.jsonl (every signal evaluation)

Usage:
    python3 v10_analytics.py summary
    python3 v10_analytics.py by-confidence
    python3 v10_analytics.py by-symbol
    python3 v10_analytics.py by-regime
    python3 v10_analytics.py mfe-mae
    python3 v10_analytics.py shadow
    python3 v10_analytics.py rejects
    python3 v10_analytics.py all          # run every report

Designed to be dependency-light: standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_TRADES = "logs/v10/trades_v10.jsonl"
DEFAULT_SHADOWS = "logs/v10/shadow_trades.jsonl"
DEFAULT_SIGNALS = "logs/v10/signals_all.jsonl"


# ------------------------------------------------------------------ IO
def _read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _f(x, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


# ------------------------------------------------------------------ stats helpers
def _bucketize(value: float, edges: List[float]) -> str:
    """Return label like '0.70-0.75' for the bucket containing value."""
    for i in range(len(edges) - 1):
        if edges[i] <= value < edges[i + 1]:
            return f"{edges[i]:.2f}-{edges[i + 1]:.2f}"
    return f">={edges[-1]:.2f}"


def _aggregate(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(rows)
    n = len(rows)
    if n == 0:
        return {"n": 0}
    pnls = [_f(r.get("realized_pnl_net")) for r in rows]
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    total_pnl = sum(pnls)
    avg_pnl = total_pnl / n
    median_pnl = statistics.median(pnls) if pnls else 0.0
    win_pnls = [p for p in pnls if p > 0]
    loss_pnls = [p for p in pnls if p < 0]
    avg_win = statistics.mean(win_pnls) if win_pnls else 0.0
    avg_loss = statistics.mean(loss_pnls) if loss_pnls else 0.0
    profit_factor = (sum(win_pnls) / abs(sum(loss_pnls))) if loss_pnls else float("inf") if win_pnls else 0.0
    expectancy = avg_pnl
    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "winrate": (wins / n) if n else 0.0,
        "total_pnl": total_pnl,
        "avg_pnl": avg_pnl,
        "median_pnl": median_pnl,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
    }


def _print_table(title: str, headers: List[str], rows: List[List[Any]]) -> None:
    print(f"\n=== {title} ===")
    if not rows:
        print("(no data)")
        return
    # Compute column widths.
    widths = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(str(c)))
    fmt = " | ".join("{:<" + str(w) + "}" for w in widths)
    print(fmt.format(*headers))
    print("-+-".join("-" * w for w in widths))
    for r in rows:
        print(fmt.format(*[str(c) for c in r]))


def _fmt_money(x: float) -> str:
    return f"${x:,.2f}"


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


# ------------------------------------------------------------------ reports
def report_summary(trades_path: str) -> None:
    trades = _read_jsonl(trades_path)
    agg = _aggregate(trades)
    print("\n=== V10 OVERALL SUMMARY ===")
    if agg["n"] == 0:
        print(f"No trades found in {trades_path}")
        return
    print(f"Trades:        {agg['n']}")
    print(f"Wins/Losses:   {agg['wins']} / {agg['losses']}")
    print(f"Winrate:       {_fmt_pct(agg['winrate'])}")
    print(f"Total PnL:     {_fmt_money(agg['total_pnl'])}")
    print(f"Avg PnL:       {_fmt_money(agg['avg_pnl'])}")
    print(f"Median PnL:    {_fmt_money(agg['median_pnl'])}")
    print(f"Avg Win:       {_fmt_money(agg['avg_win'])}")
    print(f"Avg Loss:      {_fmt_money(agg['avg_loss'])}")
    print(f"Profit Factor: {agg['profit_factor']:.2f}")
    # MFE/MAE summary
    mfes = [_f(r.get("mfe_r")) for r in trades if r.get("mfe_r") is not None]
    maes = [_f(r.get("mae_r")) for r in trades if r.get("mae_r") is not None]
    exits_r = [_f(r.get("exit_r")) for r in trades if r.get("exit_r") is not None]
    if mfes:
        print(f"\nMFE/MAE (R-units, from {len(mfes)} trades):")
        print(f"  Avg MFE:  {statistics.mean(mfes):.2f}R")
        print(f"  Avg MAE:  {statistics.mean(maes):.2f}R")
        print(f"  Avg Exit: {statistics.mean(exits_r):.2f}R")
        # Giveback ratio: how much of the favorable move did we keep?
        givebacks = []
        for m, e in zip(mfes, exits_r):
            if m > 0.1:
                givebacks.append(e / m)
        if givebacks:
            print(f"  Avg keep ratio (exit/mfe): {statistics.mean(givebacks):.2%}")


def report_by_bucket(trades: List[Dict], key_fn, edges: Optional[List[float]] = None,
                      sort_label: bool = True, label: str = "bucket") -> None:
    grouped: Dict[str, List[Dict]] = defaultdict(list)
    for t in trades:
        try:
            k = key_fn(t)
        except Exception:
            continue
        if k is None:
            continue
        grouped[k].append(t)
    rows: List[List[Any]] = []
    keys = sorted(grouped.keys()) if sort_label else sorted(grouped.keys(), key=lambda x: -len(grouped[x]))
    for k in keys:
        agg = _aggregate(grouped[k])
        rows.append([
            k,
            agg["n"],
            f"{agg['wins']}/{agg['losses']}",
            _fmt_pct(agg["winrate"]),
            _fmt_money(agg["total_pnl"]),
            _fmt_money(agg["avg_pnl"]),
            f"{agg['profit_factor']:.2f}" if agg["profit_factor"] != float("inf") else "inf",
        ])
    _print_table(
        f"BY {label.upper()}",
        [label, "n", "W/L", "WR", "Total PnL", "Avg PnL", "PF"],
        rows,
    )


def report_by_confidence(trades_path: str) -> None:
    trades = _read_jsonl(trades_path)
    if not trades:
        print(f"No trades in {trades_path}")
        return
    edges = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.01]

    def _key(t: Dict) -> Optional[str]:
        sig = t.get("signal") or {}
        conf = _f(sig.get("confidence"))
        if conf <= 0:
            return None
        return _bucketize(conf, edges)

    report_by_bucket(trades, _key, label="confidence")


def report_by_symbol(trades_path: str, top_n: int = 30) -> None:
    trades = _read_jsonl(trades_path)
    if not trades:
        print(f"No trades in {trades_path}")
        return
    grouped: Dict[str, List[Dict]] = defaultdict(list)
    for t in trades:
        sym = str(t.get("symbol") or "")
        if sym:
            grouped[sym].append(t)
    sym_aggs = [(sym, _aggregate(rows)) for sym, rows in grouped.items()]
    # Sort by total PnL ascending so worst symbols are at top (visible).
    sym_aggs.sort(key=lambda x: x[1]["total_pnl"])
    rows: List[List[Any]] = []
    for sym, agg in sym_aggs[:top_n]:
        rows.append([
            sym,
            agg["n"],
            f"{agg['wins']}/{agg['losses']}",
            _fmt_pct(agg["winrate"]),
            _fmt_money(agg["total_pnl"]),
            _fmt_money(agg["avg_pnl"]),
            f"{agg['profit_factor']:.2f}" if agg["profit_factor"] != float("inf") else "inf",
        ])
    _print_table(
        f"BY SYMBOL (worst {top_n} by total PnL)",
        ["symbol", "n", "W/L", "WR", "Total PnL", "Avg PnL", "PF"],
        rows,
    )


def report_by_regime(trades_path: str) -> None:
    trades = _read_jsonl(trades_path)
    if not trades:
        print(f"No trades in {trades_path}")
        return

    def _key(t: Dict) -> Optional[str]:
        sig = t.get("signal") or {}
        return str(sig.get("regime") or "unknown")

    report_by_bucket(trades, _key, label="regime")


def report_by_side(trades_path: str) -> None:
    trades = _read_jsonl(trades_path)
    if not trades:
        return

    def _key(t: Dict) -> Optional[str]:
        return str(t.get("direction") or t.get("side") or "?")

    report_by_bucket(trades, _key, label="side")


def report_mfe_mae(trades_path: str) -> None:
    trades = _read_jsonl(trades_path)
    enriched = [t for t in trades if t.get("mfe_r") is not None]
    print("\n=== MFE / MAE / EXIT (R-units) ===")
    if not enriched:
        print("No trades with MFE/MAE data.")
        return
    print(f"Trades with MFE/MAE: {len(enriched)}")
    mfes = [_f(t.get("mfe_r")) for t in enriched]
    maes = [_f(t.get("mae_r")) for t in enriched]
    exits = [_f(t.get("exit_r")) for t in enriched]
    print(f"  MFE   p50={statistics.median(mfes):.2f}R  mean={statistics.mean(mfes):.2f}R  max={max(mfes):.2f}R")
    print(f"  MAE   p50={statistics.median(maes):.2f}R  mean={statistics.mean(maes):.2f}R  min={min(maes):.2f}R")
    print(f"  Exit  p50={statistics.median(exits):.2f}R  mean={statistics.mean(exits):.2f}R")
    # Grouped: "would tighter SL have killed many wins?" "could TP=1R catch them?"
    bigger_mfe = sum(1 for m in mfes if m > 1.0)
    bigger_mfe_2r = sum(1 for m in mfes if m > 2.0)
    print(f"\nMFE distribution:")
    print(f"  trades that hit > 1R MFE: {bigger_mfe} ({_fmt_pct(bigger_mfe / len(mfes))})")
    print(f"  trades that hit > 2R MFE: {bigger_mfe_2r} ({_fmt_pct(bigger_mfe_2r / len(mfes))})")
    # Stop violation analysis: how often did MAE go below -1R?
    deep_mae = sum(1 for m in maes if m < -1.0)
    print(f"\nMAE distribution:")
    print(f"  trades with MAE worse than -1R: {deep_mae} ({_fmt_pct(deep_mae / len(maes))})")


def report_shadows(shadow_path: str) -> None:
    shadows = _read_jsonl(shadow_path)
    print("\n=== SHADOW TRADES (rejected signals, virtual outcome) ===")
    if not shadows:
        print(f"No shadow trades in {shadow_path}")
        return
    closed = [s for s in shadows if s.get("closed")]
    print(f"Total shadow trades: {len(shadows)} ({len(closed)} closed)")
    # Outcome split
    outcomes = defaultdict(int)
    for s in closed:
        outcomes[s.get("outcome", "?")] += 1
    if outcomes:
        print("Outcomes:")
        for k, v in sorted(outcomes.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v} ({_fmt_pct(v / len(closed))})")
    # Aggregate by reject_reason
    grouped: Dict[str, List[Dict]] = defaultdict(list)
    for s in closed:
        grouped[str(s.get("reject_reason") or "unknown")].append(s)
    rows: List[List[Any]] = []
    for reason, lst in sorted(grouped.items(), key=lambda x: -len(x[1])):
        n = len(lst)
        wins = sum(1 for s in lst if _f(s.get("exit_r")) > 0)
        avg_exit_r = statistics.mean([_f(s.get("exit_r")) for s in lst]) if lst else 0.0
        avg_mfe_r = statistics.mean([_f(s.get("mfe_r")) for s in lst]) if lst else 0.0
        avg_mae_r = statistics.mean([_f(s.get("mae_r")) for s in lst]) if lst else 0.0
        rows.append([
            reason[:40],
            n,
            f"{wins}/{n - wins}",
            _fmt_pct(wins / n),
            f"{avg_exit_r:.2f}R",
            f"{avg_mfe_r:.2f}R",
            f"{avg_mae_r:.2f}R",
        ])
    _print_table(
        "SHADOW: BY REJECT REASON",
        ["reason", "n", "W/L", "WR", "Avg exit_r", "Avg mfe_r", "Avg mae_r"],
        rows,
    )


def report_rejects(signals_path: str) -> None:
    signals = _read_jsonl(signals_path)
    print("\n=== REJECT REASON HISTOGRAM (raw signal log) ===")
    if not signals:
        print(f"No signals in {signals_path}")
        return
    total = len(signals)
    allowed = sum(1 for s in signals if s.get("allow"))
    rejected = total - allowed
    print(f"Total signals: {total}")
    print(f"  allowed:  {allowed} ({_fmt_pct(allowed / total)})")
    print(f"  rejected: {rejected} ({_fmt_pct(rejected / total)})")
    counts: Dict[str, int] = defaultdict(int)
    for s in signals:
        if not s.get("allow"):
            counts[str(s.get("reject_reason") or "unknown")] += 1
    rows = [[reason[:60], n, _fmt_pct(n / max(1, rejected))]
            for reason, n in sorted(counts.items(), key=lambda x: -x[1])]
    _print_table("Reject reasons", ["reason", "count", "share"], rows)


def report_by_phase(signals_path: str) -> None:
    signals = _read_jsonl(signals_path)
    print("\n=== BY MARKET PHASE (signals_all.jsonl) ===")
    if not signals:
        print(f"No signals in {signals_path}")
        return

    with_phase = [s for s in signals if (s.get("extra") or {}).get("market_phase")]
    total = len(with_phase)
    if not total:
        print("No signals have market_phase recorded yet.")
        return

    # Anti-trend mapping
    anti_trend = {
        ("pump", "short"), ("dump", "long"), ("dump_start", "long"),
        ("dump_bottom", "long"), ("bounce", "short"),
        ("uptrend", "short"), ("downtrend", "long"),
    }
    conflicts = []
    trend_follow = []
    all_by_phase: Dict[str, Dict[str, int]] = defaultdict(lambda: {"long": 0, "short": 0})

    for s in with_phase:
        phase = s["extra"]["market_phase"]
        side = s.get("side", "?")
        all_by_phase[phase][side] += 1
        if (phase, side) in anti_trend:
            conflicts.append(s)
        elif (phase, side) in {("pump", "long"), ("dump", "short"), ("dump_start", "short"),
                                 ("uptrend", "long"), ("downtrend", "short")}:
            trend_follow.append(s)

    print(f"Signals with phase: {total}")
    print(f"  Anti-trend (model vs phase):  {len(conflicts)} ({len(conflicts)*100/max(1,total):.1f}%)")
    print(f"  Trend-following (model aligns): {len(trend_follow)} ({len(trend_follow)*100/max(1,total):.1f}%)")
    print()

    # Phase gate simulation on conflicts
    blocks = 0
    mods = 0
    unchanged = 0
    phase_rules = {
        ("pump", "short"): None,
        ("dump", "long"): None,
        ("dump_start", "long"): None,
        ("dump_bottom", "long"): 0.5,
        ("bounce", "short"): None,
        ("uptrend", "short"): 0.7,
        ("downtrend", "long"): 0.7,
    }
    for s in conflicts:
        phase = s["extra"]["market_phase"]
        side = s.get("side", "")
        rule = phase_rules.get((phase, side))
        if rule is None and (phase, side) in phase_rules:
            blocks += 1
        elif rule is not None and rule != 1.0:
            mods += 1
        else:
            unchanged += 1

    rows = []
    for phase in sorted(all_by_phase.keys()):
        d = all_by_phase[phase]
        anti = sum(1 for s in conflicts if s["extra"]["market_phase"] == phase)
        rows.append([phase, d["long"] + d["short"], d["long"], d["short"], anti])
    _print_table("PHASE DISTRIBUTION", ["phase", "total", "long", "short", "anti-trend"], rows)

    print(f"\nPhase-gate on anti-trend:")
    print(f"  Would BLOCK:   {blocks} ({blocks*100/max(1,len(conflicts)):.1f}%)")
    print(f"  Would reduce:  {mods} ({mods*100/max(1,len(conflicts)):.1f}%)")
    print(f"  No action:     {unchanged} ({unchanged*100/max(1,len(conflicts)):.1f}%)")

    if conflicts:
        c = sorted(conflicts, key=lambda s: -s.get("confidence", 0))[:10]
        print("\nTop 5 most confident anti-trend signals:")
        for s in c[:5]:
            sym = s.get("symbol", "?")
            side = s.get("side", "?")
            conf = s.get("confidence", 0)
            phase = s["extra"]["market_phase"]
            pc24 = s.get("price_change_24h")
            pc24_s = f"{pc24*100:+.1f}%" if pc24 is not None else "n/a"
            print(f"  {sym:18s} {side:5s} conf={conf:.2f} phase={phase:16s} pc24={pc24_s} allow={s.get('allow')}")


def report_health(signals_path: str, trades_path: str, shadow_path: str) -> None:
    print("\n=== V10 LOG HEALTH ===")
    for label, path in [
        ("signals_all.jsonl", signals_path),
        ("trades_v10.jsonl", trades_path),
        ("shadow_trades.jsonl", shadow_path),
    ]:
        p = Path(path)
        if p.exists():
            size = p.stat().st_size
            n = sum(1 for _ in open(p, "r", encoding="utf-8") if _.strip())
            print(f"  {label}: {n} rows, {size:,} bytes ({path})")
        else:
            print(f"  {label}: MISSING ({path})")


# ------------------------------------------------------------------ entrypoint
def main() -> None:
    ap = argparse.ArgumentParser(description="V10 research analytics CLI")
    ap.add_argument("command", choices=[
        "summary", "by-confidence", "by-symbol", "by-regime", "by-phase",
        "by-side", "mfe-mae", "shadow", "rejects", "health", "all",
    ])
    ap.add_argument("--trades", default=DEFAULT_TRADES)
    ap.add_argument("--shadows", default=DEFAULT_SHADOWS)
    ap.add_argument("--signals", default=DEFAULT_SIGNALS)
    args = ap.parse_args()

    cmd = args.command
    if cmd == "summary":
        report_summary(args.trades)
    elif cmd == "by-confidence":
        report_by_confidence(args.trades)
    elif cmd == "by-symbol":
        report_by_symbol(args.trades)
    elif cmd == "by-regime":
        report_by_regime(args.trades)
    elif cmd == "by-phase":
        report_by_phase(args.signals)
    elif cmd == "by-side":
        report_by_side(args.trades)
    elif cmd == "mfe-mae":
        report_mfe_mae(args.trades)
    elif cmd == "shadow":
        report_shadows(args.shadows)
    elif cmd == "rejects":
        report_rejects(args.signals)
    elif cmd == "health":
        report_health(args.signals, args.trades, args.shadows)
    elif cmd == "all":
        report_health(args.signals, args.trades, args.shadows)
        report_summary(args.trades)
        report_by_side(args.trades)
        report_by_confidence(args.trades)
        report_by_regime(args.trades)
        report_by_phase(args.signals)
        report_by_symbol(args.trades)
        report_mfe_mae(args.trades)
        report_rejects(args.signals)
        report_shadows(args.shadows)


if __name__ == "__main__":
    main()
