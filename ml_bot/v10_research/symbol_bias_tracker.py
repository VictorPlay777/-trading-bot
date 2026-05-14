"""SymbolBiasTracker: per-symbol long/short performance bias.

Tracks running winrate by symbol + side to identify systematic model errors
(e.g. AEROUSDT always-short bias).  Purely for logging / analytics — does NOT
gate trades.
"""
from __future__ import annotations

import json
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Optional


class SymbolBiasTracker:
    """In-memory + append-only JSONL tracker for symbol+side outcomes."""

    def __init__(self, path: str | Path, min_samples: int = 3):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._min_samples = min_samples
        # symbol -> side -> {"n": int, "wins": int, "pnl": float}
        self._counts: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(
            lambda: defaultdict(lambda: {"n": 0, "wins": 0, "pnl": 0.0})
        )
        self._load_existing()

    # ------------------------------------------------------------------ internal
    def _load_existing(self) -> None:
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    sym = rec.get("symbol", "")
                    side = rec.get("side", "")
                    if sym and side:
                        c = self._counts[sym][side]
                        c["n"] += 1
                        c["wins"] += 1 if rec.get("pnl", 0) > 0 else 0
                        c["pnl"] += rec.get("pnl", 0.0)
        except Exception:
            pass

    def _persist(self, rec: Dict[str, Any]) -> None:
        line = json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n"
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line)

    # ------------------------------------------------------------------ public API
    def record(self, symbol: str, side: str, pnl: float, trade_id: str = "") -> None:
        """Call when a real trade closes."""
        with self._lock:
            c = self._counts[symbol][side]
            c["n"] += 1
            c["wins"] += 1 if pnl > 0 else 0
            c["pnl"] += pnl
            rec = {
                "ts": time.time(),
                "symbol": symbol,
                "side": side,
                "pnl": float(pnl),
                "trade_id": trade_id,
                "running_n": c["n"],
                "running_wins": c["wins"],
                "running_pnl": round(c["pnl"], 2),
            }
            self._persist(rec)

    def bias(self, symbol: str, side: str) -> Optional[Dict[str, Any]]:
        """Return running stats for a symbol+side, or None if < min_samples."""
        with self._lock:
            c = self._counts[symbol][side]
            n = c["n"]
            if n < self._min_samples:
                return None
            wr = c["wins"] / n if n > 0 else 0.0
            return {
                "symbol": symbol,
                "side": side,
                "n": n,
                "winrate": round(wr, 3),
                "total_pnl": round(c["pnl"], 2),
                "avg_pnl": round(c["pnl"] / n, 2),
                # "bias" = how much this side under-performs the other side
                "bias_flag": "check" if wr < 0.3 and n >= 5 else None,
            }

    def all_biases(self) -> Dict[str, Dict[str, Any]]:
        """Return every symbol+side that has >= min_samples."""
        out: Dict[str, Dict[str, Any]] = {}
        with self._lock:
            for sym, sides in self._counts.items():
                for side, c in sides.items():
                    n = c["n"]
                    if n >= self._min_samples:
                        wr = c["wins"] / n if n > 0 else 0.0
                        out[f"{sym}:{side}"] = {
                            "n": n,
                            "winrate": round(wr, 3),
                            "total_pnl": round(c["pnl"], 2),
                        }
        return out


import time  # noqa: E402
