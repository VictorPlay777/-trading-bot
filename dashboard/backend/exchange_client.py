from __future__ import annotations

import time
from pathlib import Path

import yaml

from dashboard.store import Store


class ExchangeClient:
    def __init__(self, store: Store, config_path: str, repo_root: Path):
        self.store = store
        self.config_path = config_path
        self.repo_root = repo_root
        self._exchange = None
        self.available = False
        self.last_ok_ts = None
        self.last_error = None
        self._last_error_event_ts = 0.0

    def _record_error(self, message):
        self.available = False
        self.last_error = str(message)
        now = time.time()
        if now - self._last_error_event_ts >= 300:
            self.store.insert_event(
                now,
                "ERROR",
                "BYBIT_CONNECTION_ERROR",
                self.last_error,
                metadata={"config_path": self.config_path},
            )
            self._last_error_event_ts = now

    def _load(self):
        if self._exchange is not None:
            return self._exchange
        try:
            from trader.exchange_demo import Exchange

            config_file = Path(self.config_path)
            if not config_file.is_absolute():
                config_file = self.repo_root / config_file
            with config_file.open("r", encoding="utf-8") as handle:
                cfg = yaml.safe_load(handle) or {}
            self._exchange = Exchange(cfg)
            self.available = True
            return self._exchange
        except Exception as exc:
            self._record_error(exc)
            return None

    def _call(self, method, *args, **kwargs):
        exchange = self._load()
        if exchange is None:
            return None
        try:
            result = getattr(exchange, method)(*args, **kwargs)
            self.available = True
            self.last_ok_ts = time.time()
            self.last_error = None
            return result
        except Exception as exc:
            self._record_error(exc)
            return None

    def wallet(self):
        return self._call("get_wallet_balance")

    def positions(self):
        return self._call("get_positions")

    def open_orders(self, symbol):
        return self._call("get_open_orders", symbol)

    def cancel_order(self, symbol, order_id):
        return self._call("cancel_order", symbol, order_id)

    def close_position(self, symbol, side, qty):
        return self._call("market_reduce_only", symbol, side, qty)

    def ticker(self, symbol):
        return self._call("fetch_ticker_symbol", symbol)
