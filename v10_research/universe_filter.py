"""
UniverseFilter: select TOP-N Bybit linear-perp USDT symbols ranked by a
composite score of liquidity (24h turnover) and volatility (high-low range
relative to mid price).

The filter is refreshed periodically (default once per hour) and cached so
that hot-path calls are O(1).

Score formula (default, configurable):
    score = log10(turnover_24h_usdt + 1) * (range_24h_pct ** 0.5)

Why log on turnover: prevents BTC/ETH from drowning everything else.
Why sqrt on range: dampens outliers (e.g. one wild spike).

The filter uses the Bybit /v5/market/tickers payload exposed by the bot's
exchange wrapper (`ex.fetch_tickers()` or similar). If your exchange wrapper
returns tickers under a different shape, adapt _extract_metrics().
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence


@dataclass
class SymbolMetrics:
    symbol: str
    turnover_24h: float
    range_24h_pct: float
    score: float
    last_price: float


class UniverseFilter:
    def __init__(
        self,
        top_n: int = 40,
        refresh_sec: int = 3600,
        min_turnover_usdt: float = 50_000_000.0,
        min_range_pct: float = 0.005,
        score_fn: Optional[Callable[[float, float], float]] = None,
    ):
        self.top_n = int(top_n)
        self.refresh_sec = int(refresh_sec)
        self.min_turnover = float(min_turnover_usdt)
        self.min_range_pct = float(min_range_pct)
        self.score_fn = score_fn or self._default_score
        self._lock = threading.Lock()
        self._cached_symbols: List[str] = []
        self._cached_metrics: Dict[str, SymbolMetrics] = {}
        self._last_refresh: float = 0.0

    @staticmethod
    def _default_score(turnover: float, range_pct: float) -> float:
        if turnover <= 0 or range_pct <= 0:
            return 0.0
        return math.log10(turnover + 1.0) * math.sqrt(range_pct)

    @staticmethod
    def _f(x, default: float = 0.0) -> float:
        try:
            if x is None:
                return default
            return float(x)
        except Exception:
            return default

    def _extract_metrics(self, ticker_row: Dict[str, Any]) -> Optional[SymbolMetrics]:
        """Extract turnover and range from a Bybit /v5 ticker row."""
        symbol = ticker_row.get("symbol")
        if not symbol or not isinstance(symbol, str) or not symbol.endswith("USDT"):
            return None
        turnover = self._f(ticker_row.get("turnover24h"))
        last_price = self._f(ticker_row.get("lastPrice"))
        high = self._f(ticker_row.get("highPrice24h"))
        low = self._f(ticker_row.get("lowPrice24h"))
        if last_price <= 0 or turnover < self.min_turnover:
            return None
        # Range as fraction of midpoint.
        mid = (high + low) / 2.0 if (high > 0 and low > 0) else last_price
        range_pct = (high - low) / mid if mid > 0 else 0.0
        if range_pct < self.min_range_pct:
            return None
        score = self.score_fn(turnover, range_pct)
        return SymbolMetrics(
            symbol=symbol,
            turnover_24h=turnover,
            range_24h_pct=range_pct,
            score=score,
            last_price=last_price,
        )

    def refresh(self, tickers: Sequence[Dict[str, Any]]) -> List[str]:
        """Recompute the universe from a fresh ticker list. Returns chosen symbols."""
        scored: List[SymbolMetrics] = []
        for row in tickers:
            try:
                m = self._extract_metrics(row)
            except Exception:
                m = None
            if m:
                scored.append(m)
        scored.sort(key=lambda x: x.score, reverse=True)
        chosen = scored[: self.top_n]
        with self._lock:
            self._cached_symbols = [m.symbol for m in chosen]
            self._cached_metrics = {m.symbol: m for m in chosen}
            self._last_refresh = time.time()
        return list(self._cached_symbols)

    def maybe_refresh(self, fetch_tickers_fn: Callable[[], Sequence[Dict[str, Any]]]) -> List[str]:
        """Refresh only if cache is stale; otherwise return cached symbols."""
        now = time.time()
        if (now - self._last_refresh) < self.refresh_sec and self._cached_symbols:
            return list(self._cached_symbols)
        try:
            tickers = fetch_tickers_fn() or []
        except Exception:
            return list(self._cached_symbols)
        return self.refresh(tickers)

    def symbols(self) -> List[str]:
        with self._lock:
            return list(self._cached_symbols)

    def metrics_for(self, symbol: str) -> Optional[SymbolMetrics]:
        with self._lock:
            return self._cached_metrics.get(symbol)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "top_n": self.top_n,
                "refresh_sec": self.refresh_sec,
                "cached_count": len(self._cached_symbols),
                "last_refresh": self._last_refresh,
            }
