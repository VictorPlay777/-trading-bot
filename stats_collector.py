"""
v7 Stats Collector: per-signal and per-trade logging + aggregates.

Goal: understand where model edge begins (by confidence bucket)
and whether any symbols exhibit stable positive expectancy.

Writes:
- logs/signal_log.csv  (every evaluated signal, allowed or blocked)
- logs/trade_log.csv   (one row per closed trade)
- logs/stats_by_symbol.json      (per-symbol aggregate + per-bucket breakdown)
- logs/stats_by_confidence.json  (global per-bucket breakdown)

Thread-safe writes via a lock. Atomic JSON replace.
"""
from __future__ import annotations

import csv
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger


# Confidence buckets (inclusive lower bound, exclusive upper bound, last is inclusive upper).
BUCKETS = [
    ("0.55-0.60", 0.55, 0.60),
    ("0.60-0.65", 0.60, 0.65),
    ("0.65-0.70", 0.65, 0.70),
    ("0.70-0.75", 0.70, 0.75),
    ("0.75+",     0.75, 1.01),
]


def bucket_of(conf: float) -> str:
    """Return bucket label for the given confidence value.

    Values below 0.55 are placed in a synthetic '<0.55' bucket so that
    we still log them (useful when thresholds are lowered at runtime).
    """
    try:
        c = float(conf or 0.0)
    except Exception:
        return "<0.55"
    if c < 0.55:
        return "<0.55"
    for name, lo, hi in BUCKETS:
        if lo <= c < hi:
            return name
    return "0.75+"


class StatsCollector:
    SIGNAL_CSV_HEADERS = [
        "timestamp",
        "symbol",
        "direction",
        "confidence",
        "bucket",
        "score",
        "ev",
        "regime",
        "agreement",
        "adx",
        "atr",
        "spread_bps",
        "depth_usdt",
        "funding_rate",
        "allow_entry",
        "reason",
    ]

    TRADE_CSV_HEADERS = [
        "timestamp_open",
        "timestamp_close",
        "duration_sec",
        "symbol",
        "side",
        "entry_price",
        "exit_price",
        "qty",
        "notional_entry",
        "pnl_usdt",
        "pnl_pct",
        "result",
        # ML / signal context
        "confidence",
        "bucket",
        "score",
        "ev",
        "regime",
        "agreement",
        "adx",
        "atr",
        "spread_bps",
        "funding_rate",
        "exit_reason",
        "strategy_id",
    ]

    def __init__(self, logs_dir: Optional[str] = None, stats_print_every: int = 20):
        # Resolve logs dir: allow override, fall back to <this file>/logs
        base = Path(__file__).parent
        self.logs_dir = Path(logs_dir) if logs_dir else (base / "logs")
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.signal_csv = self.logs_dir / "signal_log.csv"
        self.trade_csv = self.logs_dir / "trade_log.csv"
        self.symbol_json = self.logs_dir / "stats_by_symbol.json"
        self.bucket_json = self.logs_dir / "stats_by_confidence.json"
        self.stats_print_every = int(stats_print_every)
        self._lock = threading.Lock()

        self._ensure_csv_header(self.signal_csv, self.SIGNAL_CSV_HEADERS)
        self._ensure_csv_header(self.trade_csv, self.TRADE_CSV_HEADERS)

        # In-memory aggregates (reloaded from disk if present).
        self.by_symbol: Dict[str, Dict[str, Any]] = {}
        self.by_bucket: Dict[str, Dict[str, Any]] = {}
        self._load_aggregates()
        self.total_trades = sum(int(v.get("trades", 0)) for v in self.by_bucket.values())

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _ensure_csv_header(path: Path, headers):
        if path.exists() and path.stat().st_size > 0:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(headers)

    def _load_aggregates(self):
        try:
            if self.symbol_json.exists():
                self.by_symbol = json.loads(self.symbol_json.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[STATS] failed to load by_symbol: {e}")
            self.by_symbol = {}
        try:
            if self.bucket_json.exists():
                self.by_bucket = json.loads(self.bucket_json.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[STATS] failed to load by_bucket: {e}")
            self.by_bucket = {}

    def _save_aggregates(self):
        try:
            tmp1 = self.symbol_json.with_suffix(".json.tmp")
            tmp1.write_text(json.dumps(self.by_symbol, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp1, self.symbol_json)
            tmp2 = self.bucket_json.with_suffix(".json.tmp")
            tmp2.write_text(json.dumps(self.by_bucket, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp2, self.bucket_json)
        except Exception as e:
            logger.warning(f"[STATS] save aggregates failed: {e}")

    @staticmethod
    def _safe_float(x, default=0.0) -> float:
        try:
            return float(x)
        except Exception:
            return default

    # ---------------------------------------------------------------- API

    def log_signal(self, sig: dict, allow: bool, reason: str):
        """Append one row per evaluated signal (allowed or blocked)."""
        try:
            conf = self._safe_float(sig.get("confidence"))
            row = [
                time.time(),
                sig.get("symbol", ""),
                sig.get("direction", ""),
                round(conf, 4),
                bucket_of(conf),
                round(self._safe_float(sig.get("score")), 4),
                round(self._safe_float(sig.get("ev")), 6),
                sig.get("regime", ""),
                int(self._safe_float(sig.get("agreement"))),
                round(self._safe_float(sig.get("adx")), 2),
                round(self._safe_float(sig.get("atr")), 8),
                round(self._safe_float(sig.get("spread_bps")), 2),
                round(self._safe_float(sig.get("depth_usdt")), 2),
                round(self._safe_float(sig.get("funding_rate")), 6),
                bool(allow),
                str(reason or ""),
            ]
            with self._lock, open(self.signal_csv, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(row)
        except Exception as e:
            logger.debug(f"[STATS] log_signal failed: {e}")

    def log_trade_close(self, *, record: dict, realized_pnl_net: float, exit_reason: str = "",
                         exit_price: float = 0.0):
        """Append closed trade row and update aggregates.

        `record` should match the `_record_closed_trade` schema of selective_ml_bot,
        i.e. include fields like symbol, direction, entry_price, qty_total,
        opened_ts, closed_ts, signal (with confidence/score/ev/regime/agreement/atr/spread_bps/adx/funding_rate), etc.
        """
        try:
            signal_meta = dict(record.get("signal") or {})
            conf = self._safe_float(signal_meta.get("confidence"))
            bucket = bucket_of(conf)
            symbol = record.get("symbol", "")
            side = record.get("direction", "")
            entry = self._safe_float(record.get("entry_price"))
            qty_total = self._safe_float(record.get("qty_total"))
            notional = self._safe_float(record.get("notional_entry"))
            opened_ts = self._safe_float(record.get("opened_ts"))
            closed_ts = self._safe_float(record.get("closed_ts"))
            duration = self._safe_float(record.get("duration_sec"))
            pnl_usd = self._safe_float(realized_pnl_net)
            pnl_pct = (pnl_usd / notional * 100.0) if notional > 0 else 0.0
            # Result: threshold 0 after net fees (realized_pnl_net).
            if pnl_usd > 0:
                result = "WIN"
            elif pnl_usd < 0:
                result = "LOSS"
            else:
                result = "FLAT"

            row = [
                opened_ts,
                closed_ts,
                duration,
                symbol,
                side,
                round(entry, 10),
                round(self._safe_float(exit_price), 10),
                qty_total,
                round(notional, 4),
                round(pnl_usd, 6),
                round(pnl_pct, 4),
                result,
                round(conf, 4),
                bucket,
                round(self._safe_float(signal_meta.get("score")), 4),
                round(self._safe_float(signal_meta.get("ev")), 6),
                signal_meta.get("regime", ""),
                int(self._safe_float(signal_meta.get("agreement"))),
                round(self._safe_float(signal_meta.get("adx")), 2),
                round(self._safe_float(signal_meta.get("atr")), 8),
                round(self._safe_float(signal_meta.get("spread_bps")), 2),
                round(self._safe_float(signal_meta.get("funding_rate")), 6),
                str(exit_reason or ""),
                record.get("strategy_id", ""),
            ]
            with self._lock:
                with open(self.trade_csv, "a", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow(row)
                self._update_aggregate(symbol, bucket, conf, pnl_usd, result)
                self.total_trades += 1
                self._save_aggregates()

                if self.stats_print_every > 0 and self.total_trades % self.stats_print_every == 0:
                    self._print_stats_snapshot()
        except Exception as e:
            logger.warning(f"[STATS] log_trade_close failed: {e}")

    # ---------------------------------------------------------------- aggregates

    def _update_aggregate(self, symbol: str, bucket: str, conf: float, pnl_usd: float, result: str):
        is_win = 1 if result == "WIN" else 0

        # Global per-bucket
        b = self.by_bucket.setdefault(bucket, {"trades": 0, "wins": 0, "pnl_sum": 0.0, "conf_sum": 0.0})
        b["trades"] = int(b.get("trades", 0)) + 1
        b["wins"] = int(b.get("wins", 0)) + is_win
        b["pnl_sum"] = float(b.get("pnl_sum", 0.0)) + pnl_usd
        b["conf_sum"] = float(b.get("conf_sum", 0.0)) + conf
        b["winrate"] = b["wins"] / b["trades"] if b["trades"] else 0.0
        b["avg_pnl"] = b["pnl_sum"] / b["trades"] if b["trades"] else 0.0
        b["avg_confidence"] = b["conf_sum"] / b["trades"] if b["trades"] else 0.0

        # Per-symbol + nested per-bucket
        s = self.by_symbol.setdefault(symbol, {
            "total_trades": 0, "wins": 0, "pnl_sum": 0.0, "conf_sum": 0.0, "buckets": {},
        })
        s["total_trades"] = int(s.get("total_trades", 0)) + 1
        s["wins"] = int(s.get("wins", 0)) + is_win
        s["pnl_sum"] = float(s.get("pnl_sum", 0.0)) + pnl_usd
        s["conf_sum"] = float(s.get("conf_sum", 0.0)) + conf
        s["winrate"] = s["wins"] / s["total_trades"] if s["total_trades"] else 0.0
        s["avg_pnl"] = s["pnl_sum"] / s["total_trades"] if s["total_trades"] else 0.0
        s["avg_confidence"] = s["conf_sum"] / s["total_trades"] if s["total_trades"] else 0.0

        sb = s["buckets"].setdefault(bucket, {"trades": 0, "wins": 0, "pnl_sum": 0.0})
        sb["trades"] = int(sb.get("trades", 0)) + 1
        sb["wins"] = int(sb.get("wins", 0)) + is_win
        sb["pnl_sum"] = float(sb.get("pnl_sum", 0.0)) + pnl_usd
        sb["winrate"] = sb["wins"] / sb["trades"] if sb["trades"] else 0.0
        sb["avg_pnl"] = sb["pnl_sum"] / sb["trades"] if sb["trades"] else 0.0

    def _print_stats_snapshot(self):
        total = sum(int(v.get("trades", 0)) for v in self.by_bucket.values())
        if total == 0:
            return
        wins = sum(int(v.get("wins", 0)) for v in self.by_bucket.values())
        wr = wins / total if total else 0.0

        # Best/worst bucket by avg_pnl among buckets with >=5 trades (fallback: any).
        def pick(cmp_better):
            candidates = [(k, v) for k, v in self.by_bucket.items() if int(v.get("trades", 0)) >= 5]
            if not candidates:
                candidates = list(self.by_bucket.items())
            if not candidates:
                return "-", 0.0, 0
            best_k, best_v = candidates[0]
            for k, v in candidates[1:]:
                if cmp_better(float(v.get("avg_pnl", 0.0)), float(best_v.get("avg_pnl", 0.0))):
                    best_k, best_v = k, v
            return best_k, float(best_v.get("avg_pnl", 0.0)), int(best_v.get("trades", 0))

        best_k, best_pnl, best_n = pick(lambda a, b: a > b)
        worst_k, worst_pnl, worst_n = pick(lambda a, b: a < b)

        try:
            logger.info(
                "=== STATS UPDATE === "
                f"Total trades: {total} | Winrate: {wr*100:.1f}% | "
                f"Best bucket: {best_k} (avg_pnl={best_pnl:+.2f}, n={best_n}) | "
                f"Worst bucket: {worst_k} (avg_pnl={worst_pnl:+.2f}, n={worst_n})"
            )
            # Per-bucket breakdown (compact).
            parts = []
            for name, _, _ in BUCKETS:
                v = self.by_bucket.get(name)
                if not v:
                    continue
                parts.append(
                    f"{name}: n={int(v.get('trades',0))} wr={float(v.get('winrate',0))*100:.1f}% "
                    f"avg_pnl={float(v.get('avg_pnl',0)):+.2f}"
                )
            if parts:
                logger.info("[STATS BUCKETS] " + " | ".join(parts))
        except Exception as e:
            logger.debug(f"[STATS] print snapshot failed: {e}")
