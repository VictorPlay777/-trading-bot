"""
MFEMAETracker: track Maximum Favorable / Adverse Excursion for every position
in R-units, where 1R == |entry_price - stop_loss_price|.

For each trade we record:
- mfe_r: best move (in R) the price made in the favorable direction since entry
- mae_r: worst move (in R) the price made in the adverse direction since entry
- exit_r: realised exit P&L in R-units

This is THE most important diagnostic for TP/SL calibration:
- mfe_r > tp_r consistently => TP is too tight, leaving money on the table
- mae_r >> -1 consistently  => SL gets violated by noise; tighter timing or wider SL
- Large mfe_r but small exit_r => systematic giveback (need trailing or earlier TP)

The tracker is in-memory; final values land in trades_v10.jsonl on close.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class TradeExcursion:
    trade_id: str
    symbol: str
    side: str  # "long" or "short"
    entry_price: float
    stop_loss_price: float
    take_profit_price: float
    opened_ts: float
    last_update_ts: float = 0.0
    mfe_price: float = 0.0  # best price seen so far (in favorable direction)
    mae_price: float = 0.0  # worst price seen so far (in adverse direction)
    mfe_r: float = 0.0
    mae_r: float = 0.0
    samples: int = 0  # how many ticks have updated this trade
    # Full price history for this trade. Each entry: (ts, price).
    # Rate-limited inside update() to avoid one entry per millisecond.
    samples_history: List[Tuple[float, float]] = field(default_factory=list)
    _last_sample_ts: float = 0.0
    extras: Dict[str, float] = field(default_factory=dict)

    def r_unit(self) -> float:
        return max(1e-12, abs(self.entry_price - self.stop_loss_price))

    def update(self, price: float, sample_min_interval_sec: float = 1.0, max_samples: int = 5000) -> None:
        if price <= 0:
            return
        now = time.time()
        # Initialise on first sample.
        if self.samples == 0:
            self.mfe_price = price
            self.mae_price = price
            self.samples_history.append((now, float(price)))
            self._last_sample_ts = now
        if self.side == "long":
            if price > self.mfe_price:
                self.mfe_price = price
            if price < self.mae_price:
                self.mae_price = price
            self.mfe_r = (self.mfe_price - self.entry_price) / self.r_unit()
            self.mae_r = (self.mae_price - self.entry_price) / self.r_unit()
        else:  # short
            if price < self.mfe_price:
                self.mfe_price = price
            if price > self.mae_price:
                self.mae_price = price
            self.mfe_r = (self.entry_price - self.mfe_price) / self.r_unit()
            self.mae_r = (self.entry_price - self.mae_price) / self.r_unit()
        self.samples += 1
        self.last_update_ts = now
        # Append to history with rate-limit (default: max 1 sample/sec) and hard cap.
        if (now - self._last_sample_ts) >= sample_min_interval_sec and len(self.samples_history) < max_samples:
            self.samples_history.append((now, float(price)))
            self._last_sample_ts = now

    def to_dict(self, include_history: bool = False) -> Dict:
        d = {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "entry_price": self.entry_price,
            "stop_loss_price": self.stop_loss_price,
            "take_profit_price": self.take_profit_price,
            "opened_ts": self.opened_ts,
            "last_update_ts": self.last_update_ts,
            "mfe_price": self.mfe_price,
            "mae_price": self.mae_price,
            "mfe_r": self.mfe_r,
            "mae_r": self.mae_r,
            "samples": self.samples,
            "extras": self.extras,
        }
        if include_history:
            # Round price to 8 decimals for compactness; ts to 3 decimals (ms).
            d["samples_history"] = [
                (round(ts, 3), round(p, 10)) for ts, p in self.samples_history
            ]
        return d


class MFEMAETracker:
    """Container of TradeExcursion keyed by trade_id."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._trades: Dict[str, TradeExcursion] = {}

    def open(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss_price: float,
        take_profit_price: float,
        opened_ts: Optional[float] = None,
    ) -> None:
        with self._lock:
            self._trades[trade_id] = TradeExcursion(
                trade_id=trade_id,
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                opened_ts=opened_ts or time.time(),
            )

    def update(self, trade_id: str, price: float) -> None:
        with self._lock:
            tr = self._trades.get(trade_id)
            if tr is not None:
                tr.update(price)

    def update_by_symbol(self, symbol: str, price: float) -> None:
        """Update all open trades for a given symbol with the latest price."""
        with self._lock:
            for tr in self._trades.values():
                if tr.symbol == symbol:
                    tr.update(price)

    def get(self, trade_id: str) -> Optional[TradeExcursion]:
        with self._lock:
            return self._trades.get(trade_id)

    def close(self, trade_id: str, include_history: bool = False) -> Optional[Dict]:
        """Pop and return final excursion stats. If include_history, returns full price trace."""
        with self._lock:
            tr = self._trades.pop(trade_id, None)
            return tr.to_dict(include_history=include_history) if tr else None

    def all(self) -> Dict[str, Dict]:
        with self._lock:
            return {tid: tr.to_dict() for tid, tr in self._trades.items()}
