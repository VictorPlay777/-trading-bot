#!/usr/bin/env python3
import csv
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trader.exchange_demo import Exchange

V7_START_UTC = datetime(2026, 5, 5, 13, 41, 26, tzinfo=timezone.utc)
V7_START_MS = int(V7_START_UTC.timestamp() * 1000)
V7_START_TS = V7_START_MS / 1000.0

BUCKETS = [
    ("<0.55", 0.0, 0.55),
    ("0.55-0.60", 0.55, 0.60),
    ("0.60-0.65", 0.60, 0.65),
    ("0.65-0.70", 0.65, 0.70),
    ("0.70-0.75", 0.70, 0.75),
    ("0.75+", 0.75, 999.0),
]


def bucket(conf):
    try:
        c = float(conf or 0.0)
    except Exception:
        c = 0.0
    for name, lo, hi in BUCKETS:
        if lo <= c < hi:
            return name
    return "0.75+"


def fnum(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def dt(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def fetch_closed_pnl(ex, start_ms, end_ms):
    rows = []
    cursor = None
    while True:
        params = {
            "category": "linear",
            "startTime": str(start_ms),
            "endTime": str(end_ms),
            "limit": "100",
        }
        if cursor:
            params["cursor"] = cursor
        resp = ex._request("GET", "/v5/position/closed-pnl", params, auth=True)
        items = resp.get("result", {}).get("list", [])
        rows.extend(items)
        cursor = resp.get("result", {}).get("nextPageCursor")
        if not cursor or not items:
            break
    return rows


def load_trade_meta(logs_dir):
    path = logs_dir / "trades.jsonl"
    rows = []
    if not path.exists():
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if "v7" not in str(r.get("strategy_id", "")):
                continue
            if fnum(r.get("opened_ts")) < V7_START_TS:
                continue
            rows.append(r)
    return rows


def load_signals(logs_dir):
    path = logs_dir / "signal_log.csv"
    rows = []
    if not path.exists():
        return rows
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if fnum(r.get("timestamp")) < V7_START_TS:
                continue
            rows.append(r)
    return rows


def summarize_closed_pnl(rows):
    by_sym = defaultdict(lambda: {
        "closed_n": 0,
        "closed_pnl": 0.0,
        "wins": 0,
        "losses": 0,
        "flats": 0,
        "best": -10**18,
        "worst": 10**18,
        "buy_close_n": 0,
        "sell_close_n": 0,
        "first_close": None,
        "last_close": None,
    })
    for r in rows:
        sym = r.get("symbol", "")
        pnl = fnum(r.get("closedPnl"))
        ts = int(r.get("updatedTime") or r.get("createdTime") or 0)
        s = by_sym[sym]
        s["closed_n"] += 1
        s["closed_pnl"] += pnl
        s["best"] = max(s["best"], pnl)
        s["worst"] = min(s["worst"], pnl)
        if pnl > 0:
            s["wins"] += 1
        elif pnl < 0:
            s["losses"] += 1
        else:
            s["flats"] += 1
        side = str(r.get("side", ""))
        if side == "Buy":
            s["buy_close_n"] += 1
        elif side == "Sell":
            s["sell_close_n"] += 1
        if ts:
            s["first_close"] = ts if s["first_close"] is None else min(s["first_close"], ts)
            s["last_close"] = ts if s["last_close"] is None else max(s["last_close"], ts)
    return by_sym


def summarize_trade_meta(rows):
    by_sym = defaultdict(lambda: {
        "trade_log_n": 0,
        "trade_log_valid_pnl_n": 0,
        "trade_log_pnl_sum": 0.0,
        "meta_n": 0,
        "conf_sum": 0.0,
        "conf_min": 999.0,
        "conf_max": 0.0,
        "dir": Counter(),
        "regime": Counter(),
        "bucket": Counter(),
        "pnl_source": Counter(),
    })
    for r in rows:
        sym = r.get("symbol", "")
        s = by_sym[sym]
        s["trade_log_n"] += 1
        source = r.get("pnl_source") or "missing"
        s["pnl_source"][source] += 1
        if r.get("pnl_source"):
            s["trade_log_valid_pnl_n"] += 1
            s["trade_log_pnl_sum"] += fnum(r.get("realized_pnl_net"))
        sig = r.get("signal") or {}
        conf = fnum(sig.get("confidence"))
        if conf > 0:
            s["meta_n"] += 1
            s["conf_sum"] += conf
            s["conf_min"] = min(s["conf_min"], conf)
            s["conf_max"] = max(s["conf_max"], conf)
            s["bucket"][bucket(conf)] += 1
        if r.get("direction"):
            s["dir"][str(r.get("direction"))] += 1
        if sig.get("regime"):
            s["regime"][str(sig.get("regime"))] += 1
    return by_sym


def summarize_signals(rows):
    by_sym = defaultdict(lambda: {
        "signals": 0,
        "allowed": 0,
        "blocked": 0,
        "sig_conf_sum": 0.0,
        "sig_conf_n": 0,
        "sig_bucket": Counter(),
        "sig_dir": Counter(),
        "sig_regime": Counter(),
        "block_reasons": Counter(),
    })
    for r in rows:
        sym = r.get("symbol", "")
        s = by_sym[sym]
        s["signals"] += 1
        conf = fnum(r.get("confidence"))
        s["sig_conf_sum"] += conf
        s["sig_conf_n"] += 1
        s["sig_bucket"][bucket(conf)] += 1
        if r.get("direction"):
            s["sig_dir"][r.get("direction")] += 1
        if r.get("regime"):
            s["sig_regime"][r.get("regime")] += 1
        allow = str(r.get("allow_entry", "")).lower() in ("true", "1", "yes")
        if allow:
            s["allowed"] += 1
        else:
            s["blocked"] += 1
            s["block_reasons"][r.get("reason", "")] += 1
    return by_sym


def top_counter(c, n=3):
    if not c:
        return "-"
    return ";".join(f"{k}:{v}" for k, v in c.most_common(n))


def main():
    root = Path(__file__).resolve().parent
    logs_dir = root / "logs"
    cfg = yaml.safe_load(open(root / "config.yaml", "r", encoding="utf-8"))
    ex = Exchange(cfg)

    end_ms = int(time.time() * 1000)
    closed_rows = fetch_closed_pnl(ex, V7_START_MS, end_ms)
    trade_rows = load_trade_meta(logs_dir)
    signal_rows = load_signals(logs_dir)

    closed = summarize_closed_pnl(closed_rows)
    meta = summarize_trade_meta(trade_rows)
    signals = summarize_signals(signal_rows)

    symbols = sorted(set(closed) | set(meta) | set(signals))
    report_rows = []
    for sym in symbols:
        c = closed.get(sym, {})
        m = meta.get(sym, {})
        sg = signals.get(sym, {})
        closed_n = int(c.get("closed_n", 0) or 0)
        wins = int(c.get("wins", 0) or 0)
        losses = int(c.get("losses", 0) or 0)
        winrate = wins / closed_n if closed_n else 0.0
        meta_n = int(m.get("meta_n", 0) or 0)
        avg_conf = (m.get("conf_sum", 0.0) / meta_n) if meta_n else 0.0
        sig_n = int(sg.get("signals", 0) or 0)
        sig_avg_conf = (sg.get("sig_conf_sum", 0.0) / sg.get("sig_conf_n", 1)) if sg.get("sig_conf_n", 0) else 0.0
        report_rows.append({
            "symbol": sym,
            "closed_pnl_bybit": float(c.get("closed_pnl", 0.0) or 0.0),
            "closed_n_bybit": closed_n,
            "winrate_bybit": winrate,
            "wins_bybit": wins,
            "losses_bybit": losses,
            "best_closed_pnl": float(c.get("best", 0.0) if closed_n else 0.0),
            "worst_closed_pnl": float(c.get("worst", 0.0) if closed_n else 0.0),
            "buy_close_n": int(c.get("buy_close_n", 0) or 0),
            "sell_close_n": int(c.get("sell_close_n", 0) or 0),
            "first_close_utc": dt(c.get("first_close")) if c.get("first_close") else "",
            "last_close_utc": dt(c.get("last_close")) if c.get("last_close") else "",
            "trade_log_n": int(m.get("trade_log_n", 0) or 0),
            "trade_log_valid_pnl_n": int(m.get("trade_log_valid_pnl_n", 0) or 0),
            "trade_log_valid_pnl_sum": float(m.get("trade_log_pnl_sum", 0.0) or 0.0),
            "meta_n": meta_n,
            "avg_conf_trade_meta": avg_conf,
            "min_conf_trade_meta": float(m.get("conf_min", 0.0) if meta_n else 0.0),
            "max_conf_trade_meta": float(m.get("conf_max", 0.0) if meta_n else 0.0),
            "trade_dirs": top_counter(m.get("dir", Counter()), 4),
            "trade_regimes": top_counter(m.get("regime", Counter()), 4),
            "trade_buckets": top_counter(m.get("bucket", Counter()), 6),
            "pnl_sources": top_counter(m.get("pnl_source", Counter()), 5),
            "signals_total": sig_n,
            "signals_allowed": int(sg.get("allowed", 0) or 0),
            "signals_blocked": int(sg.get("blocked", 0) or 0),
            "signal_avg_conf": sig_avg_conf,
            "signal_dirs": top_counter(sg.get("sig_dir", Counter()), 4),
            "signal_regimes": top_counter(sg.get("sig_regime", Counter()), 4),
            "signal_buckets": top_counter(sg.get("sig_bucket", Counter()), 6),
            "top_block_reasons": top_counter(sg.get("block_reasons", Counter()), 5),
        })

    report_rows.sort(key=lambda r: r["closed_pnl_bybit"], reverse=True)
    out_csv = logs_dir / "v7_all_symbols_report.csv"
    out_txt = logs_dir / "v7_all_symbols_report.txt"
    if report_rows:
        with open(out_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(report_rows[0].keys()))
            writer.writeheader()
            writer.writerows(report_rows)

    total_pnl = sum(r["closed_pnl_bybit"] for r in report_rows)
    total_closed = sum(r["closed_n_bybit"] for r in report_rows)
    total_wins = sum(r["wins_bybit"] for r in report_rows)
    total_losses = sum(r["losses_bybit"] for r in report_rows)
    valid_meta = sum(r["meta_n"] for r in report_rows)
    total_signals = sum(r["signals_total"] for r in report_rows)
    total_allowed = sum(r["signals_allowed"] for r in report_rows)

    lines = []
    lines.append("=" * 120)
    lines.append("V7 ALL SYMBOLS REPORT")
    lines.append("=" * 120)
    lines.append(f"v7_start_utc: {V7_START_UTC.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"bybit_closed_symbols: {len([r for r in report_rows if r['closed_n_bybit'] > 0])}")
    lines.append(f"bybit_closed_trades: {total_closed}")
    lines.append(f"bybit_closed_pnl: {total_pnl:+.2f} USDT")
    lines.append(f"bybit_winrate: {(total_wins / total_closed * 100.0) if total_closed else 0.0:.2f}% wins={total_wins} losses={total_losses}")
    lines.append(f"trade_meta_rows_with_conf: {valid_meta}")
    lines.append(f"signals_total: {total_signals} allowed={total_allowed} blocked={total_signals - total_allowed}")
    lines.append("")
    lines.append("NOTE:")
    lines.append("- closed_pnl_bybit / winrate_bybit are the most reliable realized PnL metrics.")
    lines.append("- trade confidence/regime metadata before the PnL fix may be incomplete or not perfectly matched to Bybit closed-pnl rows.")
    lines.append("- restored positions after restart may have conf=0/regime empty and should not be used for bucket conclusions.")
    lines.append("")

    def add_table(title, rows):
        lines.append(title)
        lines.append("-" * 120)
        lines.append(f"{'symbol':18s} {'pnl':>12s} {'n':>5s} {'wr%':>7s} {'avg':>10s} {'best':>10s} {'worst':>10s} {'meta_n':>7s} {'avg_conf':>9s} {'allowed':>8s} {'signals':>8s}")
        for r in rows:
            n = r["closed_n_bybit"]
            avg = r["closed_pnl_bybit"] / n if n else 0.0
            lines.append(
                f"{r['symbol']:18s} {r['closed_pnl_bybit']:>+12.2f} {n:>5d} {r['winrate_bybit']*100:>7.1f} "
                f"{avg:>+10.2f} {r['best_closed_pnl']:>+10.2f} {r['worst_closed_pnl']:>+10.2f} "
                f"{r['meta_n']:>7d} {r['avg_conf_trade_meta']:>9.3f} {r['signals_allowed']:>8d} {r['signals_total']:>8d}"
            )
        lines.append("")

    add_table("TOP PROFIT SYMBOLS BY BYBIT CLOSED PNL", report_rows[:30])
    add_table("TOP LOSS SYMBOLS BY BYBIT CLOSED PNL", sorted(report_rows, key=lambda r: r["closed_pnl_bybit"])[:30])

    lines.append("DETAILS: confidence buckets / regimes / signal funnel")
    lines.append("-" * 120)
    for r in report_rows:
        if r["closed_n_bybit"] <= 0 and r["signals_total"] <= 0:
            continue
        lines.append(
            f"{r['symbol']}: pnl={r['closed_pnl_bybit']:+.2f} n={r['closed_n_bybit']} wr={r['winrate_bybit']*100:.1f}% "
            f"meta_n={r['meta_n']} avg_conf={r['avg_conf_trade_meta']:.3f} "
            f"trade_dirs=[{r['trade_dirs']}] regimes=[{r['trade_regimes']}] buckets=[{r['trade_buckets']}] "
            f"pnl_sources=[{r['pnl_sources']}] signals={r['signals_total']} allowed={r['signals_allowed']} "
            f"signal_buckets=[{r['signal_buckets']}] block=[{r['top_block_reasons']}]"
        )

    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:90]))
    print(f"\nReports written:")
    print(f"  {out_txt}")
    print(f"  {out_csv}")


if __name__ == "__main__":
    main()
