#!/usr/bin/env python3
"""
Full statistics analyzer for selective_ml_bot trades.

Reads:
  - logs/trade_log.csv      (v7 CSV)
  - logs/trades.jsonl       (all versions, fallback)
  - logs/signal_log.csv     (v7 signal-level)
  - logs/stats_by_*.json    (live aggregates, optional)

Outputs a multi-section report to stdout and writes:
  - logs/report.txt
  - logs/report_by_symbol.csv
  - logs/report_by_bucket.csv
  - logs/report_by_regime.csv
  - logs/report_by_hour.csv

Usage on server:
  cd ~/-trading-bot
  source venv/bin/activate
  python3 analyze_stats.py                    # default: ml_bot/logs
  python3 analyze_stats.py --logs ml_bot/logs --min-trades 5
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


BUCKETS = [
    ("<0.55",     0.00, 0.55),
    ("0.55-0.60", 0.55, 0.60),
    ("0.60-0.65", 0.60, 0.65),
    ("0.65-0.70", 0.65, 0.70),
    ("0.70-0.75", 0.70, 0.75),
    ("0.75+",     0.75, 1.01),
]


def bucket_of(conf: float) -> str:
    try:
        c = float(conf or 0.0)
    except Exception:
        return "<0.55"
    for name, lo, hi in BUCKETS:
        if lo <= c < hi:
            return name
    return "0.75+"


def fnum(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


# ----------------------------------------------------------------- loaders


def load_csv_trades(path: Path) -> list:
    if not path.exists() or path.stat().st_size == 0:
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append({
                "ts_open": fnum(r.get("timestamp_open")),
                "ts_close": fnum(r.get("timestamp_close")),
                "duration": fnum(r.get("duration_sec")),
                "symbol": r.get("symbol", ""),
                "side": r.get("side", ""),
                "entry": fnum(r.get("entry_price")),
                "exit": fnum(r.get("exit_price")),
                "qty": fnum(r.get("qty")),
                "notional": fnum(r.get("notional_entry")),
                "pnl": fnum(r.get("pnl_usdt")),
                "pnl_pct": fnum(r.get("pnl_pct")),
                "result": r.get("result", ""),
                "conf": fnum(r.get("confidence")),
                "bucket": r.get("bucket") or bucket_of(fnum(r.get("confidence"))),
                "score": fnum(r.get("score")),
                "ev": fnum(r.get("ev")),
                "regime": r.get("regime", ""),
                "agreement": int(fnum(r.get("agreement"))),
                "adx": fnum(r.get("adx")),
                "atr": fnum(r.get("atr")),
                "spread_bps": fnum(r.get("spread_bps")),
                "funding_rate": fnum(r.get("funding_rate")),
                "exit_reason": r.get("exit_reason", ""),
                "strategy_id": r.get("strategy_id", ""),
            })
    return out


def load_jsonl_trades(path: Path) -> list:
    """Fallback when CSV is empty (older versions wrote only JSONL)."""
    if not path.exists() or path.stat().st_size == 0:
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            sig = rec.get("signal") or {}
            entry = fnum(rec.get("entry_price"))
            qty = fnum(rec.get("qty_total"))
            notional = entry * qty
            pnl = fnum(rec.get("realized_pnl_net"))
            pnl_pct = (pnl / notional * 100.0) if notional > 0 else 0.0
            result = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "FLAT")
            er_list = rec.get("exit_reasons") or []
            exit_reason = er_list[-1].get("reason", "") if er_list else ""
            conf = fnum(sig.get("confidence"))
            out.append({
                "ts_open": fnum(rec.get("opened_ts")),
                "ts_close": fnum(rec.get("closed_ts")),
                "duration": fnum(rec.get("duration_sec")),
                "symbol": rec.get("symbol", ""),
                "side": rec.get("direction", ""),
                "entry": entry,
                "exit": 0.0,
                "qty": qty,
                "notional": notional,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "result": result,
                "conf": conf,
                "bucket": bucket_of(conf),
                "score": fnum(sig.get("score")),
                "ev": fnum(sig.get("ev")),
                "regime": sig.get("regime", ""),
                "agreement": int(fnum(sig.get("agreement"))),
                "adx": fnum(sig.get("adx")),
                "atr": fnum(sig.get("atr")),
                "spread_bps": fnum(sig.get("spread_bps")),
                "funding_rate": fnum(sig.get("funding_rate")),
                "exit_reason": exit_reason,
                "strategy_id": rec.get("strategy_id", ""),
            })
    return out


def load_signals_csv(path: Path) -> list:
    if not path.exists() or path.stat().st_size == 0:
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append({
                "ts": fnum(r.get("timestamp")),
                "symbol": r.get("symbol", ""),
                "direction": r.get("direction", ""),
                "conf": fnum(r.get("confidence")),
                "bucket": r.get("bucket") or bucket_of(fnum(r.get("confidence"))),
                "ev": fnum(r.get("ev")),
                "regime": r.get("regime", ""),
                "allow": str(r.get("allow_entry", "")).lower() == "true",
                "reason": r.get("reason", ""),
            })
    return out


# ---------------------------------------------------------------- aggregation


def agg_group(trades, key_fn):
    g = defaultdict(list)
    for t in trades:
        g[key_fn(t)].append(t)
    return g


def stats_block(trades):
    n = len(trades)
    if n == 0:
        return None
    wins = sum(1 for t in trades if t["pnl"] > 0)
    losses = sum(1 for t in trades if t["pnl"] < 0)
    flats = n - wins - losses
    total_pnl = sum(t["pnl"] for t in trades)
    avg_pnl = total_pnl / n
    win_pnls = [t["pnl"] for t in trades if t["pnl"] > 0]
    loss_pnls = [t["pnl"] for t in trades if t["pnl"] < 0]
    avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0.0
    avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0.0
    sum_win = sum(win_pnls)
    sum_loss = abs(sum(loss_pnls))
    profit_factor = (sum_win / sum_loss) if sum_loss > 0 else float("inf") if sum_win > 0 else 0.0
    expectancy = avg_pnl  # in USDT per trade
    avg_dur = sum(t["duration"] for t in trades) / n
    avg_conf = sum(t["conf"] for t in trades) / n
    avg_pnl_pct = sum(t["pnl_pct"] for t in trades) / n
    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "flats": flats,
        "winrate": (wins / (wins + losses)) if (wins + losses) > 0 else 0.0,
        "total_pnl": total_pnl,
        "avg_pnl": avg_pnl,
        "avg_pnl_pct": avg_pnl_pct,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "avg_dur_sec": avg_dur,
        "avg_conf": avg_conf,
    }


def fmt_pct(x):
    return f"{x*100:.1f}%"


def fmt_usd(x):
    return f"{x:+.2f}"


def render_table(rows, headers, sort_key=None, reverse=True):
    if sort_key:
        rows = sorted(rows, key=sort_key, reverse=reverse)
    # Compute widths
    widths = [len(h) for h in headers]
    cells = [[str(c) for c in r] for r in rows]
    for r in cells:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(c))
    out = []
    sep = "  "
    out.append(sep.join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    out.append(sep.join("-" * widths[i] for i in range(len(headers))))
    for r in cells:
        out.append(sep.join(r[i].ljust(widths[i]) for i in range(len(headers))))
    return "\n".join(out)


# ---------------------------------------------------------------- report


def build_report(trades, signals, min_trades=1, top=20):
    out = io.StringIO()
    p = lambda *a: print(*a, file=out)

    if not trades:
        p("No trades found. Nothing to analyze.")
        return out.getvalue()

    # Strategy split
    strat_groups = agg_group(trades, lambda t: t["strategy_id"] or "unknown")
    strategies = sorted(strat_groups.keys())

    # Time range
    ts_min = min(t["ts_open"] for t in trades if t["ts_open"]) if trades else 0
    ts_max = max(t["ts_close"] for t in trades if t["ts_close"]) if trades else 0
    fmt_ts = lambda ts: datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if ts else "-"

    p("=" * 78)
    p("FULL STATISTICS REPORT")
    p("=" * 78)
    p(f"Trades total : {len(trades)}")
    p(f"Time range   : {fmt_ts(ts_min)}  ->  {fmt_ts(ts_max)}")
    p(f"Strategies   : {', '.join(strategies)}")
    if signals:
        p(f"Signals total: {len(signals)} (allowed={sum(1 for s in signals if s['allow'])})")
    p()

    # ---------------- OVERALL
    s = stats_block(trades)
    p("--- OVERALL ---")
    p(f"  trades        : {s['n']}")
    p(f"  wins/losses   : {s['wins']} / {s['losses']} (flat={s['flats']})")
    p(f"  winrate       : {fmt_pct(s['winrate'])}")
    p(f"  total PnL     : {fmt_usd(s['total_pnl'])} USDT")
    p(f"  avg PnL/trade : {fmt_usd(s['avg_pnl'])} USDT  ({s['avg_pnl_pct']:+.3f}%)")
    p(f"  avg win/loss  : {fmt_usd(s['avg_win'])}  /  {fmt_usd(s['avg_loss'])}")
    pf = s['profit_factor']
    p(f"  profit factor : {pf:.2f}" if pf != float('inf') else "  profit factor : INF (no losses)")
    p(f"  avg duration  : {s['avg_dur_sec']/60:.1f} min")
    p(f"  avg confidence: {s['avg_conf']:.3f}")
    p()

    # ---------------- BY STRATEGY
    if len(strategies) > 1:
        p("--- BY STRATEGY ---")
        rows = []
        for st in strategies:
            sb = stats_block(strat_groups[st])
            rows.append([
                st, sb["n"], f"{sb['wins']}/{sb['losses']}",
                fmt_pct(sb["winrate"]), fmt_usd(sb["total_pnl"]),
                fmt_usd(sb["avg_pnl"]), f"{sb['profit_factor']:.2f}",
            ])
        p(render_table(rows, ["strategy", "n", "W/L", "winrate", "total_pnl", "avg_pnl", "PF"], sort_key=lambda r: r[1]))
        p()

    # ---------------- BY BUCKET (confidence)
    p("--- BY CONFIDENCE BUCKET ---")
    bg = agg_group(trades, lambda t: t["bucket"])
    rows = []
    bucket_order = {b[0]: i for i, b in enumerate(BUCKETS)}
    for bk in sorted(bg.keys(), key=lambda x: bucket_order.get(x, 99)):
        sb = stats_block(bg[bk])
        rows.append([
            bk, sb["n"], f"{sb['wins']}/{sb['losses']}",
            fmt_pct(sb["winrate"]), fmt_usd(sb["total_pnl"]),
            fmt_usd(sb["avg_pnl"]), f"{sb['avg_pnl_pct']:+.3f}%",
            f"{sb['profit_factor']:.2f}", f"{sb['avg_conf']:.3f}",
        ])
    p(render_table(rows, ["bucket", "n", "W/L", "winrate", "total_pnl", "avg_pnl_usd", "avg_pnl_pct", "PF", "avg_conf"]))
    p()

    # CSV per bucket
    bucket_csv_rows = []
    for bk, lst in bg.items():
        sb = stats_block(lst)
        bucket_csv_rows.append({
            "bucket": bk, "trades": sb["n"], "wins": sb["wins"], "losses": sb["losses"],
            "winrate": round(sb["winrate"], 4), "total_pnl_usdt": round(sb["total_pnl"], 2),
            "avg_pnl_usdt": round(sb["avg_pnl"], 4), "avg_pnl_pct": round(sb["avg_pnl_pct"], 4),
            "profit_factor": round(sb["profit_factor"] if sb["profit_factor"] != float("inf") else -1, 4),
            "avg_conf": round(sb["avg_conf"], 4),
        })

    # ---------------- BY REGIME
    p("--- BY REGIME ---")
    rg = agg_group(trades, lambda t: t["regime"] or "?")
    rows = []
    for k in sorted(rg.keys()):
        sb = stats_block(rg[k])
        rows.append([
            k, sb["n"], f"{sb['wins']}/{sb['losses']}",
            fmt_pct(sb["winrate"]), fmt_usd(sb["total_pnl"]),
            fmt_usd(sb["avg_pnl"]), f"{sb['profit_factor']:.2f}",
        ])
    p(render_table(rows, ["regime", "n", "W/L", "winrate", "total_pnl", "avg_pnl", "PF"], sort_key=lambda r: r[1]))
    p()

    regime_csv_rows = []
    for k, lst in rg.items():
        sb = stats_block(lst)
        regime_csv_rows.append({
            "regime": k, "trades": sb["n"], "wins": sb["wins"], "losses": sb["losses"],
            "winrate": round(sb["winrate"], 4), "total_pnl_usdt": round(sb["total_pnl"], 2),
            "avg_pnl_usdt": round(sb["avg_pnl"], 4),
            "profit_factor": round(sb["profit_factor"] if sb["profit_factor"] != float("inf") else -1, 4),
        })

    # ---------------- BY SIDE
    p("--- BY SIDE (long/short) ---")
    sg = agg_group(trades, lambda t: t["side"] or "?")
    rows = []
    for k in sorted(sg.keys()):
        sb = stats_block(sg[k])
        rows.append([
            k, sb["n"], f"{sb['wins']}/{sb['losses']}",
            fmt_pct(sb["winrate"]), fmt_usd(sb["total_pnl"]),
            fmt_usd(sb["avg_pnl"]), f"{sb['profit_factor']:.2f}",
        ])
    p(render_table(rows, ["side", "n", "W/L", "winrate", "total_pnl", "avg_pnl", "PF"], sort_key=lambda r: r[1]))
    p()

    # ---------------- BY EXIT REASON
    p("--- BY EXIT REASON ---")
    eg = agg_group(trades, lambda t: t["exit_reason"] or "?")
    rows = []
    for k in sorted(eg.keys()):
        sb = stats_block(eg[k])
        rows.append([
            k, sb["n"], f"{sb['wins']}/{sb['losses']}",
            fmt_pct(sb["winrate"]), fmt_usd(sb["total_pnl"]),
            fmt_usd(sb["avg_pnl"]),
        ])
    p(render_table(rows, ["exit_reason", "n", "W/L", "winrate", "total_pnl", "avg_pnl"], sort_key=lambda r: r[1]))
    p()

    # ---------------- BY HOUR OF DAY (UTC)
    p("--- BY HOUR OF DAY (UTC) ---")
    hg = defaultdict(list)
    for t in trades:
        if t["ts_open"]:
            h = datetime.fromtimestamp(t["ts_open"], tz=timezone.utc).hour
            hg[h].append(t)
    rows = []
    for h in sorted(hg.keys()):
        sb = stats_block(hg[h])
        rows.append([
            f"{h:02d}", sb["n"], f"{sb['wins']}/{sb['losses']}",
            fmt_pct(sb["winrate"]), fmt_usd(sb["total_pnl"]), fmt_usd(sb["avg_pnl"]),
        ])
    p(render_table(rows, ["hour_utc", "n", "W/L", "winrate", "total_pnl", "avg_pnl"], sort_key=lambda r: int(r[0]), reverse=False))
    p()

    hour_csv_rows = []
    for h, lst in hg.items():
        sb = stats_block(lst)
        hour_csv_rows.append({
            "hour_utc": h, "trades": sb["n"], "wins": sb["wins"], "losses": sb["losses"],
            "winrate": round(sb["winrate"], 4), "total_pnl_usdt": round(sb["total_pnl"], 2),
            "avg_pnl_usdt": round(sb["avg_pnl"], 4),
        })

    # ---------------- BY SYMBOL
    p(f"--- BY SYMBOL (min_trades={min_trades}, top {top}) ---")
    symg = agg_group(trades, lambda t: t["symbol"] or "?")
    sym_rows_full = []
    for sym, lst in symg.items():
        sb = stats_block(lst)
        sym_rows_full.append((sym, sb))

    # Top by total PnL
    rows_top = sorted(sym_rows_full, key=lambda x: x[1]["total_pnl"], reverse=True)
    rows_top = [(s, sb) for s, sb in rows_top if sb["n"] >= min_trades][:top]
    p(f"  TOP {top} by total_pnl:")
    rows = [[s, sb["n"], f"{sb['wins']}/{sb['losses']}", fmt_pct(sb["winrate"]),
             fmt_usd(sb["total_pnl"]), fmt_usd(sb["avg_pnl"]),
             f"{sb['profit_factor']:.2f}", f"{sb['avg_conf']:.3f}"]
            for s, sb in rows_top]
    p(render_table(rows, ["symbol", "n", "W/L", "winrate", "total_pnl", "avg_pnl", "PF", "avg_conf"]))
    p()

    # Worst by total PnL
    rows_worst = sorted(sym_rows_full, key=lambda x: x[1]["total_pnl"])
    rows_worst = [(s, sb) for s, sb in rows_worst if sb["n"] >= min_trades][:top]
    p(f"  WORST {top} by total_pnl:")
    rows = [[s, sb["n"], f"{sb['wins']}/{sb['losses']}", fmt_pct(sb["winrate"]),
             fmt_usd(sb["total_pnl"]), fmt_usd(sb["avg_pnl"]),
             f"{sb['profit_factor']:.2f}", f"{sb['avg_conf']:.3f}"]
            for s, sb in rows_worst]
    p(render_table(rows, ["symbol", "n", "W/L", "winrate", "total_pnl", "avg_pnl", "PF", "avg_conf"]))
    p()

    # Best winrate (with min trades)
    rows_wr = [(s, sb) for s, sb in sym_rows_full if sb["n"] >= max(min_trades, 5)]
    rows_wr.sort(key=lambda x: x[1]["winrate"], reverse=True)
    if rows_wr:
        p(f"  TOP {top} by winrate (min n>={max(min_trades,5)}):")
        rows = [[s, sb["n"], f"{sb['wins']}/{sb['losses']}", fmt_pct(sb["winrate"]),
                 fmt_usd(sb["total_pnl"]), fmt_usd(sb["avg_pnl"]),
                 f"{sb['avg_conf']:.3f}"]
                for s, sb in rows_wr[:top]]
        p(render_table(rows, ["symbol", "n", "W/L", "winrate", "total_pnl", "avg_pnl", "avg_conf"]))
        p()

    # CSV per-symbol full
    sym_csv_rows = []
    for s, sb in sym_rows_full:
        sym_csv_rows.append({
            "symbol": s, "trades": sb["n"], "wins": sb["wins"], "losses": sb["losses"],
            "winrate": round(sb["winrate"], 4),
            "total_pnl_usdt": round(sb["total_pnl"], 2),
            "avg_pnl_usdt": round(sb["avg_pnl"], 4),
            "avg_pnl_pct": round(sb["avg_pnl_pct"], 4),
            "profit_factor": round(sb["profit_factor"] if sb["profit_factor"] != float("inf") else -1, 4),
            "avg_conf": round(sb["avg_conf"], 4),
        })

    # ---------------- BUCKET x SIDE
    p("--- BUCKET x SIDE ---")
    bsg = agg_group(trades, lambda t: (t["bucket"], t["side"]))
    rows = []
    for (bk, side), lst in sorted(bsg.items(), key=lambda x: (bucket_order.get(x[0][0], 99), x[0][1])):
        sb = stats_block(lst)
        rows.append([
            bk, side, sb["n"], f"{sb['wins']}/{sb['losses']}",
            fmt_pct(sb["winrate"]), fmt_usd(sb["total_pnl"]), fmt_usd(sb["avg_pnl"]),
        ])
    p(render_table(rows, ["bucket", "side", "n", "W/L", "winrate", "total_pnl", "avg_pnl"]))
    p()

    # ---------------- SIGNAL FUNNEL
    if signals:
        p("--- SIGNAL FUNNEL (why entries are blocked) ---")
        total_sigs = len(signals)
        allowed = sum(1 for s in signals if s["allow"])
        rejected = total_sigs - allowed
        p(f"  total signals : {total_sigs}")
        p(f"  allowed       : {allowed} ({allowed/total_sigs*100:.1f}%)")
        p(f"  rejected      : {rejected} ({rejected/total_sigs*100:.1f}%)")

        reason_counts = defaultdict(int)
        for s in signals:
            if s["allow"]:
                continue
            # Take only the leading reason key (before any '(' or ' ').
            key = s["reason"].split("(")[0].strip() or "?"
            reason_counts[key] += 1
        rows = []
        for k, v in sorted(reason_counts.items(), key=lambda x: -x[1]):
            rows.append([k, v, f"{v/rejected*100:.1f}%" if rejected else "-"])
        p(render_table(rows, ["reject_reason", "count", "share"]))
        p()

        # Allowed signals per bucket
        p("--- ALLOWED SIGNALS PER BUCKET ---")
        bg2 = defaultdict(lambda: {"total": 0, "allow": 0})
        for s in signals:
            bg2[s["bucket"]]["total"] += 1
            if s["allow"]:
                bg2[s["bucket"]]["allow"] += 1
        rows = []
        for bk in sorted(bg2.keys(), key=lambda x: bucket_order.get(x, 99)):
            v = bg2[bk]
            share = (v["allow"] / v["total"] * 100) if v["total"] else 0.0
            rows.append([bk, v["total"], v["allow"], f"{share:.1f}%"])
        p(render_table(rows, ["bucket", "evaluated", "allowed", "allow_rate"]))
        p()

    return out.getvalue(), bucket_csv_rows, sym_csv_rows, regime_csv_rows, hour_csv_rows


def write_csv(path: Path, rows, fieldnames):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default="ml_bot/logs", help="Path to logs directory")
    ap.add_argument("--min-trades", type=int, default=1, help="Min trades per symbol for tables")
    ap.add_argument("--top", type=int, default=20, help="Top N rows per ranking")
    args = ap.parse_args()

    logs = Path(args.logs)
    if not logs.exists():
        # Fallback: if user runs without ml_bot/ prefix
        alt = Path("logs")
        if alt.exists():
            logs = alt
        else:
            print(f"ERROR: logs dir not found: {args.logs}")
            return 1

    csv_path = logs / "trade_log.csv"
    jsonl_path = logs / "trades.jsonl"
    sig_path = logs / "signal_log.csv"

    trades_csv = load_csv_trades(csv_path)
    trades_jsonl = load_jsonl_trades(jsonl_path)
    # Prefer CSV (richer fields, unambiguous). Fall back to JSONL if CSV empty.
    trades = trades_csv if trades_csv else trades_jsonl
    signals = load_signals_csv(sig_path)

    print(f"Loaded: csv_trades={len(trades_csv)}  jsonl_trades={len(trades_jsonl)}  signals={len(signals)}")
    print(f"Using {'CSV' if trades_csv else 'JSONL'} as primary trade source.")
    print()

    result = build_report(trades, signals, min_trades=args.min_trades, top=args.top)
    if isinstance(result, tuple):
        report, bucket_rows, sym_rows, regime_rows, hour_rows = result
    else:
        report = result
        bucket_rows = sym_rows = regime_rows = hour_rows = []

    print(report)

    out_dir = logs
    (out_dir / "report.txt").write_text(report, encoding="utf-8")
    write_csv(out_dir / "report_by_bucket.csv", bucket_rows,
              ["bucket","trades","wins","losses","winrate","total_pnl_usdt","avg_pnl_usdt","avg_pnl_pct","profit_factor","avg_conf"])
    write_csv(out_dir / "report_by_symbol.csv", sym_rows,
              ["symbol","trades","wins","losses","winrate","total_pnl_usdt","avg_pnl_usdt","avg_pnl_pct","profit_factor","avg_conf"])
    write_csv(out_dir / "report_by_regime.csv", regime_rows,
              ["regime","trades","wins","losses","winrate","total_pnl_usdt","avg_pnl_usdt","profit_factor"])
    write_csv(out_dir / "report_by_hour.csv", hour_rows,
              ["hour_utc","trades","wins","losses","winrate","total_pnl_usdt","avg_pnl_usdt"])

    print(f"Reports written to: {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
