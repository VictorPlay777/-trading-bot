"""
ShadowTracker: virtually simulate every rejected signal as if it had been taken.

For each rejected signal we:
1. Record entry conditions (price, ATR, SL/TP from the same formula).
2. On every subsequent monitor tick, update MFE/MAE.
3. Close the shadow trade when:
   - price touches TP   (-> outcome="tp")
   - price touches SL   (-> outcome="sl")
   - max-hold expires   (-> outcome="timeout")

The result lands in shadow_trades.jsonl with the original reject_reason. This
lets us answer questions like:
- "Are signals rejected by 'cooldown' systematically profitable?"
- "Do conf<0.75 short signals work in chop regime?"
- "What's the expectancy of any reject_reason bucket?"

Implementation notes:
- Pure Python, no external deps.
- One ShadowTrade per (symbol, side, entry_ts) — same symbol can have
  multiple concurrent shadows of opposite directions.
- Pricing uses bot's own ticker fetches; no extra exchange calls.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ShadowTrade:
    shadow_id: str
    symbol: str
    side: str  # long/short
    entry_price: float
    stop_loss_price: float
    take_profit_price: float
    opened_ts: float
    max_hold_sec: int
    confidence: float
    score: float
    ev: float
    regime: str
    reject_reason: str
    feature_hash: Optional[str] = None
    # Live state
    last_price: float = 0.0
    last_update_ts: float = 0.0
    mfe_price: float = 0.0
    mae_price: float = 0.0
    mfe_r: float = 0.0
    mae_r: float = 0.0
    samples: int = 0
    # Final state (populated on close)
    closed: bool = False
    closed_ts: float = 0.0
    exit_price: float = 0.0
    exit_r: float = 0.0
    outcome: str = ""  # "tp" | "sl" | "timeout"

    def r_unit(self) -> float:
        return max(1e-12, abs(self.entry_price - self.stop_loss_price))

    def update(self, price: float, now_ts: float) -> Optional[str]:
        """Update internal MFE/MAE, then check exit conditions.

        Returns the outcome string if the trade should be closed now, else None.
        """
        if self.closed or price <= 0:
            return None
        # Initialise tracking on first sample.
        if self.samples == 0:
            self.mfe_price = price
            self.mae_price = price
        if self.side == "long":
            self.mfe_price = max(self.mfe_price, price)
            self.mae_price = min(self.mae_price, price)
            self.mfe_r = (self.mfe_price - self.entry_price) / self.r_unit()
            self.mae_r = (self.mae_price - self.entry_price) / self.r_unit()
            tp_hit = price >= self.take_profit_price
            sl_hit = price <= self.stop_loss_price
        else:
            self.mfe_price = min(self.mfe_price, price)
            self.mae_price = max(self.mae_price, price)
            self.mfe_r = (self.entry_price - self.mfe_price) / self.r_unit()
            self.mae_r = (self.entry_price - self.mae_price) / self.r_unit()
            tp_hit = price <= self.take_profit_price
            sl_hit = price >= self.stop_loss_price
        self.last_price = price
        self.last_update_ts = now_ts
        self.samples += 1
        if tp_hit:
            return "tp"
        if sl_hit:
            return "sl"
        if (now_ts - self.opened_ts) >= self.max_hold_sec:
            return "timeout"
        return None

    def finalize(self, exit_price: float, outcome: str, now_ts: float) -> None:
        self.closed = True
        self.exit_price = exit_price
        self.outcome = outcome
        self.closed_ts = now_ts
        # Realised R.
        if self.side == "long":
            self.exit_r = (exit_price - self.entry_price) / self.r_unit()
        else:
            self.exit_r = (self.entry_price - exit_price) / self.r_unit()

    def to_dict(self) -> Dict:
        return {
            "shadow_id": self.shadow_id,
            "symbol": self.symbol,
            "side": self.side,
            "entry_price": self.entry_price,
            "stop_loss_price": self.stop_loss_price,
            "take_profit_price": self.take_profit_price,
            "opened_ts": self.opened_ts,
            "max_hold_sec": self.max_hold_sec,
            "confidence": self.confidence,
            "score": self.score,
            "ev": self.ev,
            "regime": self.regime,
            "reject_reason": self.reject_reason,
            "feature_hash": self.feature_hash,
            "last_price": self.last_price,
            "last_update_ts": self.last_update_ts,
            "mfe_r": self.mfe_r,
            "mae_r": self.mae_r,
            "samples": self.samples,
            "closed": self.closed,
            "closed_ts": self.closed_ts,
            "exit_price": self.exit_price,
            "exit_r": self.exit_r,
            "outcome": self.outcome,
        }


class ShadowTracker:
    def __init__(self, output_path: str | Path, max_hold_sec: int = 24 * 3600, max_open: int = 5000):
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_hold_sec = int(max_hold_sec)
        self.max_open = int(max_open)
        self._lock = threading.Lock()
        self._open: Dict[str, ShadowTrade] = {}

    def open_shadow(
        self,
        *,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss_price: float,
        take_profit_price: float,
        confidence: float,
        score: float,
        ev: float,
        regime: str,
        reject_reason: str,
        feature_hash: Optional[str] = None,
    ) -> Optional[str]:
        with self._lock:
            if len(self._open) >= self.max_open:
                # Backpressure: drop oldest to keep memory bounded.
                oldest = min(self._open.values(), key=lambda t: t.opened_ts)
                self._finalize_unsafe(oldest, exit_price=oldest.last_price or oldest.entry_price, outcome="dropped_capacity")
            sid = uuid.uuid4().hex[:16]
            self._open[sid] = ShadowTrade(
                shadow_id=sid,
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                opened_ts=time.time(),
                max_hold_sec=self.max_hold_sec,
                confidence=confidence,
                score=score,
                ev=ev,
                regime=regime,
                reject_reason=reject_reason,
                feature_hash=feature_hash,
            )
            return sid

    def _finalize_unsafe(self, tr: ShadowTrade, exit_price: float, outcome: str) -> None:
        tr.finalize(exit_price=exit_price, outcome=outcome, now_ts=time.time())
        # Persist
        try:
            with open(self.output_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(tr.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")
        except Exception:
            pass
        # Remove from active map
        self._open.pop(tr.shadow_id, None)

    def update_symbol(self, symbol: str, price: float) -> List[str]:
        """Update every open shadow trade for a symbol; close those that hit conditions.

        Returns a list of shadow_ids that were closed in this call (for logging).
        """
        if price <= 0:
            return []
        closed_ids: List[str] = []
        now = time.time()
        with self._lock:
            to_close: List[tuple[ShadowTrade, str]] = []
            for tr in list(self._open.values()):
                if tr.symbol != symbol:
                    continue
                outcome = tr.update(price, now)
                if outcome is not None:
                    to_close.append((tr, outcome))
            for tr, outcome in to_close:
                self._finalize_unsafe(tr, exit_price=price, outcome=outcome)
                closed_ids.append(tr.shadow_id)
        return closed_ids

    def update_all(self, prices_by_symbol: Dict[str, float]) -> List[str]:
        closed: List[str] = []
        for sym, price in prices_by_symbol.items():
            closed.extend(self.update_symbol(sym, price))
        return closed

    def open_count(self) -> int:
        with self._lock:
            return len(self._open)
