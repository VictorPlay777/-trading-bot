"""
SignalLogger: append every signal (allowed + rejected) to logs/v10/signals_all.jsonl.

This is the foundational data collection layer for v10. Every model evaluation
produces ONE row, regardless of whether the signal was acted upon.

Use cases:
- Reconstruct exactly what the model saw at any point in time
- Compute hypothetical P&L for any subset of signals
- Identify which gates are systematically rejecting profitable trades
- Build confidence/regime/symbol histograms

Schema is intentionally rich; downstream analytics decide what to read.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional


class SignalLogger:
    """Thread-safe append-only JSONL writer for every model evaluation."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # Track per-tick counts for diagnostics
        self.total_logged: int = 0
        self.total_allowed: int = 0
        self.total_rejected: int = 0

    def log(
        self,
        *,
        symbol: str,
        side: str,
        confidence: float,
        score: float,
        ev: float,
        regime: str,
        atr: float,
        atr_pct: float,
        spread_bps: Optional[float],
        volume_24h: Optional[float],
        funding_rate: Optional[float],
        btc_trend: Optional[str],
        allow: bool,
        reject_reason: Optional[str],
        size_mult: float = 1.0,
        adx: Optional[float] = None,
        agreement: Optional[int] = None,
        uncertainty: Optional[float] = None,
        depth_usdt: Optional[float] = None,
        quality_score: Optional[float] = None,
        trend_direction: Optional[str] = None,
        # v10c: temporal / market context fields for post-hoc edge detection
        hour_utc: Optional[int] = None,
        day_of_week: Optional[int] = None,
        is_weekend: Optional[bool] = None,
        price_change_1h: Optional[float] = None,
        price_change_4h: Optional[float] = None,
        price_change_24h: Optional[float] = None,
        bars_since_last_signal: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append one row. All fields explicit to avoid silent schema drift.

        v10b: added adx/agreement/uncertainty/depth_usdt/quality_score for soft-filter
        post-hoc analysis (we do not gate signals on these — we record them and
        analyse which thresholds correlate with profitable outcomes).
        """
        row: Dict[str, Any] = {
            "ts": time.time(),
            "symbol": symbol,
            "side": side,
            "confidence": float(confidence),
            "score": float(score),
            "quality_score": float(quality_score) if quality_score is not None else float(score),
            "ev": float(ev),
            "regime": regime,
            "atr": float(atr) if atr is not None else None,
            "atr_pct": float(atr_pct) if atr_pct is not None else None,
            "adx": float(adx) if adx is not None else None,
            "agreement": int(agreement) if agreement is not None else None,
            "uncertainty": float(uncertainty) if uncertainty is not None else None,
            "spread_bps": float(spread_bps) if spread_bps is not None else None,
            "depth_usdt": float(depth_usdt) if depth_usdt is not None else None,
            "volume_24h": float(volume_24h) if volume_24h is not None else None,
            "funding_rate": float(funding_rate) if funding_rate is not None else None,
            "btc_trend": btc_trend,
            "allow": bool(allow),
            "reject_reason": reject_reason,
            "size_mult": float(size_mult),
            "trend_direction": trend_direction,
            "hour_utc": hour_utc,
            "day_of_week": day_of_week,
            "is_weekend": is_weekend,
            "price_change_1h": price_change_1h,
            "price_change_4h": price_change_4h,
            "price_change_24h": price_change_24h,
            "bars_since_last_signal": bars_since_last_signal,
        }
        if extra:
            # Never overwrite primary fields with extra; namespace under 'extra'.
            row["extra"] = extra
        line = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock:
            try:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line)
                self.total_logged += 1
                if allow:
                    self.total_allowed += 1
                else:
                    self.total_rejected += 1
            except Exception:
                # Never break the trading loop on a logging failure.
                pass

    def stats(self) -> Dict[str, int]:
        return {
            "total_logged": self.total_logged,
            "total_allowed": self.total_allowed,
            "total_rejected": self.total_rejected,
        }
