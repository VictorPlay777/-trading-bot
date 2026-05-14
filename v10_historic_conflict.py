"""Analyze how often the ML model contradicted market phase (anti-trend signals)."""
import json
import os
from collections import Counter, defaultdict
from datetime import datetime

PATH = "/home/svy1990/-trading-bot/logs/v10/signals_all.jsonl"
OUT_JSON = "/home/svy1990/-trading-bot/logs/v10/historic_conflict.json"
OUT_TXT = "/home/svy1990/-trading-bot/logs/v10/historic_conflict.txt"

# Phase x Side -> is this anti-trend?
ANTI_TREND = {
    ("pump", "short"): True,
    ("pump_top", "short"): False,  # pump_top short = reversal play, could be OK
    ("parabolic_up", "short"): False,  # parabolic short = fade parabola, could be OK
    ("dump", "long"): True,
    ("dump_start", "long"): True,
    ("dump_bottom", "long"): True,
    ("parabolic_down", "long"): False,
    ("bounce", "short"): True,
    ("uptrend", "short"): True,   # short against uptrend
    ("downtrend", "long"): True,   # long against downtrend
    ("flat", "long"): False,
    ("flat", "short"): False,
}

TREND_FOLLOWING = {
    ("pump", "long"): True,
    ("dump", "short"): True,
    ("dump_start", "short"): True,
    ("uptrend", "long"): True,
    ("downtrend", "short"): True,
}

rows = []
with open(PATH) as f:
    for line in f:
        try:
            rows.append(json.loads(line))
        except Exception:
            pass

with_phase = [r for r in rows if (r.get("extra") or {}).get("market_phase")]

conflicts = []
for r in with_phase:
    phase = r["extra"]["market_phase"]
    side = r.get("side", "")
    if ANTI_TREND.get((phase, side), False):
        conflicts.append(r)

trend_signals = []
for r in with_phase:
    phase = r["extra"]["market_phase"]
    side = r.get("side", "")
    if TREND_FOLLOWING.get((phase, side), False):
        trend_signals.append(r)

total = len(with_phase)
conflict_n = len(conflicts)
trend_n = len(trend_signals)
conflict_pct = conflict_n * 100 / max(1, total)
trend_pct = trend_n * 100 / max(1, total)

lines = []
lines.append("=" * 60)
lines.append("V10 HISTORIC CONFLICT ANALYSIS")
lines.append(f"Generated: {datetime.utcnow().isoformat()}Z")
lines.append("=" * 60)
lines.append(f"Total signals with known phase: {total}")
lines.append(f"Anti-trend signals (model contradicts phase): {conflict_n} ({conflict_pct:.1f}%)")
lines.append(f"Trend-following signals (model aligns with phase): {trend_n} ({trend_pct:.1f}%)")
lines.append("")

# Breakdown by phase
by_phase = defaultdict(list)
for r in conflicts:
    by_phase[r["extra"]["market_phase"]].append(r)

lines.append("ANTI-TREND BREAKDOWN BY PHASE:")
lines.append("-" * 60)
for phase in sorted(by_phase.keys()):
    rs = by_phase[phase]
    allow_yes = sum(1 for r in rs if r.get("allow"))
    avg_conf = sum(r.get("confidence", 0) for r in rs) / max(1, len(rs))
    avg_ev = sum(r.get("ev", 0) for r in rs) / max(1, len(rs))
    lines.append(f"  {phase:16s}: {len(rs):4d} signals  avg_conf={avg_conf:.2f}  avg_ev={avg_ev:+.4f}  allow={allow_yes}/{len(rs)}")

# Distribution of ALL signals by phase (for reference)
all_by_phase = defaultdict(lambda: {"long": 0, "short": 0})
for r in with_phase:
    phase = r["extra"]["market_phase"]
    side = r.get("side", "?")
    all_by_phase[phase][side] += 1

lines.append("")
lines.append("ALL SIGNALS BY PHASE:")
lines.append("-" * 60)
for phase in sorted(all_by_phase.keys()):
    d = all_by_phase[phase]
    lines.append(f"  {phase:16s}: long={d['long']:4d}  short={d['short']:4d}")

# Most confident anti-trend signals
lines.append("")
lines.append("TOP 10 MOST CONFIDENT ANTI-TREND SIGNALS:")
lines.append("-" * 60)
conflicts_sorted = sorted(conflicts, key=lambda r: -r.get("confidence", 0))
for r in conflicts_sorted[:10]:
    sym = r.get("symbol", "?")
    side = r.get("side", "?")
    conf = r.get("confidence", 0)
    ev = r.get("ev", 0)
    phase = r["extra"]["market_phase"]
    pc24 = r.get("price_change_24h")
    allow = r.get("allow")
    pc24_s = f"{pc24*100:+.1f}%" if pc24 is not None else "n/a"
    lines.append(f"  {sym:18s} {side:5s} conf={conf:.2f} ev={ev:+.4f} phase={phase:16s} pc24={pc24_s:>7} allow={allow}")

# What phase-gate would have done to these
lines.append("")
lines.append("WHAT PHASE-GATE WOULD DO (SIMULATION):")
lines.append("-" * 60)
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
for r in conflicts:
    phase = r["extra"]["market_phase"]
    side = r.get("side", "")
    rule = phase_rules.get((phase, side))
    if rule is None and (phase, side) in phase_rules:
        blocks += 1
    elif rule is not None and rule != 1.0:
        mods += 1
    else:
        unchanged += 1

lines.append(f"  Would BLOCK:    {blocks:4d} ({blocks*100/max(1,conflict_n):.1f}%)")
lines.append(f"  Would reduce:   {mods:4d} ({mods*100/max(1,conflict_n):.1f}%)")
lines.append(f"  No action:      {unchanged:4d} ({unchanged*100/max(1,conflict_n):.1f}%)")

# Trend-following summary
lines.append("")
lines.append("TREND-FOLLOWING SIGNALS SUMMARY:")
lines.append("-" * 60)
if trend_signals:
    avg_conf = sum(r.get("confidence", 0) for r in trend_signals) / len(trend_signals)
    avg_ev = sum(r.get("ev", 0) for r in trend_signals) / len(trend_signals)
    allow_yes = sum(1 for r in trend_signals if r.get("allow"))
    lines.append(f"  avg_conf={avg_conf:.2f}  avg_ev={avg_ev:+.4f}  allow={allow_yes}/{len(trend_signals)}")
else:
    lines.append("  (no trend-following signals)")

text_report = "\n".join(lines)
print(text_report)

# Write outputs
os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
with open(OUT_TXT, "w", encoding="utf-8") as f:
    f.write(text_report + "\n")

json_report = {
    "generated_utc": datetime.utcnow().isoformat() + "Z",
    "total_signals_with_phase": total,
    "anti_trend": {
        "count": conflict_n,
        "pct": round(conflict_pct, 2),
        "by_phase": {phase: len(rs) for phase, rs in by_phase.items()},
    },
    "trend_following": {
        "count": trend_n,
        "pct": round(trend_pct, 2),
    },
    "phase_gate_simulation": {
        "would_block": blocks,
        "would_reduce": mods,
        "unchanged": unchanged,
    },
    "top_anti_trend": [
        {
            "symbol": r.get("symbol"),
            "side": r.get("side"),
            "confidence": r.get("confidence"),
            "ev": r.get("ev"),
            "phase": r["extra"]["market_phase"],
            "price_change_24h": r.get("price_change_24h"),
            "allowed": r.get("allow"),
        }
        for r in conflicts_sorted[:20]
    ],
}
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(json_report, f, indent=2, ensure_ascii=False)

print(f"\n[Saved] {OUT_TXT}")
print(f"[Saved] {OUT_JSON}")
