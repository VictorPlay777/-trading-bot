#!/usr/bin/env python3
"""
Backfill trades.jsonl from historical selective_ml_bot logs.
Parses [OPEN] and [STATE CLOSED] lines to reconstruct trades.
Run: python3 parse_log_trades.py logs/selective_ml_supervisor.log >> logs/trades.jsonl
"""
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

OPEN_RE = re.compile(
    r'\[OPEN\]\s+(\w+)\s+(long|short)\s+qty=([\d.]+)\s+entry=([\d.]+)'
)
CLOSED_RE = re.compile(
    r'\[STATE CLOSED\]\s+(\w+)\s+total=([\d.]+)\s+closed=([\d.]+)'
)
# Optional: parse TP/SL/PNL log lines if available (e.g., [EXIT] ... reason=tp1|sl|trailing|etc)
EXIT_RE = re.compile(
    r'\[EXIT\]\s+(\w+)\s+reason=(\w+)\s+qty=([\d.]+)'
)
PNL_RE = re.compile(
    r'\[PNL\]\s+(\w+)\s+cumRealisedPnl_delta=([-\d.]+)'
)

def parse_ts(line):
    # Try ISO timestamp at start, else return None
    m = re.match(r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})', line)
    if m:
        try:
            s = m.group(1).replace('T', ' ')
            dt = datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
            return dt.replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            pass
    return None

def parse_log(filepath, default_regime="unknown"):
    opens = {}   # symbol -> dict with entry data
    exits = defaultdict(list)  # symbol -> list of exit events
    pnls = defaultdict(float)  # symbol -> sum of cumRealisedPnl_delta

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            ts = parse_ts(line)
            # OPEN
            m = OPEN_RE.search(line)
            if m:
                sym, side, qty_str, entry_str = m.groups()
                opens[sym] = {
                    "ts": ts,
                    "symbol": sym,
                    "direction": side,
                    "qty": qty_str,
                    "entry": float(entry_str),
                }
                continue
            # EXIT (optional capture for reason/qty)
            m = EXIT_RE.search(line)
            if m:
                sym, reason, qty = m.groups()
                exits[sym].append({"reason": reason, "qty": qty, "ts": ts})
                continue
            # PNL delta (for realized_pnl net estimate)
            m = PNL_RE.search(line)
            if m:
                sym, delta = m.groups()
                try:
                    pnls[sym] += float(delta)
                except Exception:
                    pass
                continue
            # CLOSED state (final closure detection)
            m = CLOSED_RE.search(line)
            if m:
                sym, total, closed = m.groups()
                if sym not in opens:
                    continue  # no prior open captured
                o = opens[sym]
                closed_ts = ts or o.get("ts")
                opened_ts = o.get("ts") or closed_ts
                duration = (closed_ts - opened_ts) if (closed_ts and opened_ts) else 0.0
                qty_total = str(total)
                qty_closed = str(closed)
                # Estimate notional entry
                try:
                    notional = float(o.get("entry", 0)) * float(qty_total)
                except Exception:
                    notional = 0.0
                # Use captured PnL delta (best effort); else 0
                realized = pnls.get(sym, 0.0)
                rec = {
                    "schema": "selective_trade_backfilled_v1",
                    "trade_id": f"{sym}_{int(opened_ts or 0)}",
                    "symbol": sym,
                    "direction": o.get("direction"),
                    "opened_ts": opened_ts,
                    "closed_ts": closed_ts,
                    "duration_sec": max(0.0, duration),
                    "entry_price": o.get("entry"),
                    "qty_total": qty_total,
                    "qty_closed": qty_closed,
                    "leverage": None,
                    "stop_loss_price": None,
                    "take_profit_levels": {},
                    "signal": {
                        "confidence": None,
                        "score": None,
                        "ev": None,
                        "regime": default_regime,
                        "agreement": None,
                        "uncertainty": None,
                        "spread_bps": None,
                        "depth_usdt": None,
                        "atr": None,
                        "size_mult": None,
                    },
                    "exit_reasons": exits.get(sym, []),
                    "exit_reason_qty_sum": {},
                    "cum_realised_pnl_entry": 0.0,
                    "cum_realised_pnl_close": None,
                    "realized_pnl_net": realized,
                    "entry_fees_est": 0.0,
                    "exit_fees_est": 0.0,
                    "funding_estimate": 0.0,
                    "notional_entry": notional,
                }
                # Prepare aggregated exit reasons by qty
                er_sum = {}
                for er in rec["exit_reasons"]:
                    try:
                        r = er.get("reason", "unknown")
                        q = float(er.get("qty", 0) or 0)
                        er_sum[r] = er_sum.get(r, 0.0) + q
                    except Exception:
                        pass
                rec["exit_reason_qty_sum"] = er_sum
                print(json.dumps(rec, ensure_ascii=False, default=str))
                # Cleanup
                if sym in opens:
                    del opens[sym]
                if sym in exits:
                    del exits[sym]
                if sym in pnls:
                    del pnls[sym]
    # Any leftovers (still open) are ignored

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 parse_log_trades.py logs/selective_ml_supervisor.log > logs/trades_backfill.jsonl", file=sys.stderr)
        sys.exit(1)
    logfile = sys.argv[1]
    parse_log(logfile)
