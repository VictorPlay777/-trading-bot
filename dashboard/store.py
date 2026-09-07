from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id TEXT PRIMARY KEY,
    strategy_id TEXT,
    symbol TEXT,
    side TEXT,
    opened_ts REAL,
    closed_ts REAL,
    duration_sec REAL,
    entry_price REAL,
    exit_price REAL,
    qty REAL,
    notional REAL,
    leverage INTEGER,
    stop_loss REAL,
    tp1 REAL,
    tp2 REAL,
    tp3 REAL,
    pnl REAL,
    pnl_pct REAL,
    pnl_source TEXT,
    fees_est REAL,
    fees_actual REAL,
    funding_est REAL,
    r_multiple REAL,
    exit_reason TEXT,
    exit_reasons_json TEXT,
    signal_json TEXT,
    raw_json TEXT,
    confidence REAL,
    regime TEXT,
    ev REAL,
    score REAL,
    updated_ts REAL
);
CREATE INDEX IF NOT EXISTS idx_trades_closed_ts ON trades(closed_ts);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_strategy_id ON trades(strategy_id);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL,
    symbol TEXT,
    direction TEXT,
    confidence REAL,
    score REAL,
    ev REAL,
    regime TEXT,
    agreement INTEGER,
    allowed INTEGER,
    reason TEXT,
    strategy_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(ts);

CREATE TABLE IF NOT EXISTS fills (
    exec_id TEXT PRIMARY KEY,
    symbol TEXT,
    side TEXT,
    qty REAL,
    price REAL,
    fee REAL,
    fee_currency TEXT,
    is_maker INTEGER,
    ts_ms INTEGER,
    order_id TEXT,
    raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_fills_symbol_ts ON fills(symbol, ts_ms);

CREATE TABLE IF NOT EXISTS positions_live (
    symbol TEXT PRIMARY KEY,
    side TEXT,
    entry_price REAL,
    mark_price REAL,
    qty REAL,
    qty_closed REAL,
    leverage INTEGER,
    stop_loss REAL,
    tp1 REAL,
    tp2 REAL,
    tp3 REAL,
    trailing_price REAL,
    unrealized_pnl REAL,
    unrealized_pnl_pct REAL,
    r_multiple REAL,
    position_value REAL,
    cum_realised_pnl REAL,
    opened_ts REAL,
    strategy_id TEXT,
    exit_state TEXT,
    tp1_done INTEGER,
    tp2_done INTEGER,
    tp3_done INTEGER,
    signal_json TEXT,
    updated_ts REAL
);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL,
    equity REAL,
    wallet_balance REAL,
    available_balance REAL,
    unrealized_pnl REAL,
    open_positions INTEGER
);
CREATE INDEX IF NOT EXISTS idx_equity_snapshots_ts ON equity_snapshots(ts);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL,
    level TEXT,
    event_type TEXT,
    symbol TEXT,
    strategy_id TEXT,
    message TEXT,
    metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT,
    updated_ts REAL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    created_ts REAL,
    expires_ts REAL,
    user TEXT
);

CREATE TABLE IF NOT EXISTS bot_heartbeat (
    id INTEGER PRIMARY KEY CHECK(id=1),
    ts REAL,
    pid INTEGER,
    started_ts REAL,
    cycle_ms INTEGER,
    signals_generated INTEGER,
    executed_orders INTEGER,
    active_positions INTEGER,
    equity REAL,
    bybit_ok INTEGER,
    bybit_last_ok_ts REAL,
    bybit_last_error TEXT,
    paused INTEGER,
    trading_enabled INTEGER,
    strategy_id TEXT,
    config_path TEXT,
    extra_json TEXT
);
"""


class Store:
    def __init__(self, path: str | None = None):
        if path is None:
            path = os.getenv("DASHBOARD_DB_PATH")
        if not path:
            path = str(Path(__file__).resolve().parents[1] / "data" / "dashboard.db")
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.init_schema()

    def init_schema(self):
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    @staticmethod
    def _json(value: Any) -> str | None:
        return None if value is None else json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _row(row):
        return dict(row) if row is not None else None

    def upsert_trade(self, row: dict):
        columns = [
            "trade_id", "strategy_id", "symbol", "side", "opened_ts", "closed_ts",
            "duration_sec", "entry_price", "exit_price", "qty", "notional", "leverage",
            "stop_loss", "tp1", "tp2", "tp3", "pnl", "pnl_pct", "pnl_source",
            "fees_est", "fees_actual", "funding_est", "r_multiple", "exit_reason",
            "exit_reasons_json", "signal_json", "raw_json", "confidence", "regime",
            "ev", "score", "updated_ts",
        ]
        values = [row.get(column) for column in columns]
        sql = f"""
            INSERT OR REPLACE INTO trades ({", ".join(columns)})
            VALUES ({", ".join("?" for _ in columns)})
        """
        with self._lock:
            self._conn.execute(sql, values)
            self._conn.commit()

    def update_trade_pnl(self, trade_id, pnl, exit_price, pnl_source):
        with self._lock:
            self._conn.execute(
                "UPDATE trades SET pnl=?, exit_price=?, pnl_source=?, updated_ts=? WHERE trade_id=?",
                (pnl, exit_price, pnl_source, time.time(), trade_id),
            )
            self._conn.commit()

    def get_trade(self, trade_id):
        row = self._conn.execute("SELECT * FROM trades WHERE trade_id=?", (trade_id,)).fetchone()
        return self._row(row)

    def list_trades(self, filters: dict | None = None, limit=100, offset=0):
        filters = filters or {}
        clauses, params = [], []
        for field, op in (("start_ts", ">="), ("end_ts", "<=")):
            if filters.get(field) is not None:
                clauses.append(f"opened_ts {op} ?")
                params.append(filters[field])
        for field in ("symbol", "strategy_id", "side", "exit_reason"):
            if filters.get(field):
                clauses.append(f"{field} = ?")
                params.append(filters[field])
        if filters.get("result") == "win":
            clauses.append("pnl > 0")
        elif filters.get("result") == "loss":
            clauses.append("pnl <= 0")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        total = self._conn.execute(f"SELECT COUNT(*) FROM trades{where}", params).fetchone()[0]
        rows = self._conn.execute(
            f"SELECT * FROM trades{where} ORDER BY COALESCE(closed_ts, opened_ts) DESC LIMIT ? OFFSET ?",
            [*params, int(limit), int(offset)],
        ).fetchall()
        return [dict(row) for row in rows], int(total)

    def trade_filter_options(self):
        options = {}
        for key, column in (("symbols", "symbol"), ("strategies", "strategy_id"), ("exit_reasons", "exit_reason")):
            rows = self._conn.execute(
                f"SELECT DISTINCT {column} FROM trades WHERE {column} IS NOT NULL AND {column} != '' ORDER BY {column}"
            ).fetchall()
            options[key] = [row[0] for row in rows]
        return options

    def insert_signal(self, row):
        values = (
            row.get("ts", time.time()), row.get("symbol"), row.get("direction"),
            row.get("confidence"), row.get("score"), row.get("ev"), row.get("regime"),
            row.get("agreement"), row.get("allowed"), row.get("reason"), row.get("strategy_id"),
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO signals (ts,symbol,direction,confidence,score,ev,regime,agreement,allowed,reason,strategy_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                values,
            )
            self._conn.commit()

    def list_signals(self, limit=100, offset=0, filters=None):
        filters = filters or {}
        clauses, params = [], []
        for field in ("symbol", "direction", "regime", "strategy_id", "reason"):
            if filters.get(field) is not None:
                clauses.append(f"{field}=?")
                params.append(filters[field])
        for field, op in (("start_ts", ">="), ("end_ts", "<=")):
            if filters.get(field) is not None:
                clauses.append(f"ts {op} ?")
                params.append(filters[field])
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM signals{where} ORDER BY ts DESC LIMIT ? OFFSET ?",
            [*params, int(limit), int(offset)],
        ).fetchall()
        return [dict(row) for row in rows]

    def upsert_fill(self, row):
        columns = ["exec_id", "symbol", "side", "qty", "price", "fee", "fee_currency",
                   "is_maker", "ts_ms", "order_id", "raw_json"]
        values = [row.get(column) for column in columns]
        with self._lock:
            self._conn.execute(
                f"INSERT OR REPLACE INTO fills ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                values,
            )
            self._conn.commit()

    def list_fills(self, symbol=None, start_ms=None, end_ms=None):
        clauses, params = [], []
        if symbol:
            clauses.append("symbol=?")
            params.append(symbol)
        if start_ms is not None:
            clauses.append("ts_ms>=?")
            params.append(start_ms)
        if end_ms is not None:
            clauses.append("ts_ms<=?")
            params.append(end_ms)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(f"SELECT * FROM fills{where} ORDER BY ts_ms", params).fetchall()
        return [dict(row) for row in rows]

    def sum_fees(self, symbol, start_ms, end_ms):
        row = self._conn.execute(
            "SELECT COALESCE(SUM(ABS(fee)), 0) FROM fills WHERE symbol=? AND ts_ms>=? AND ts_ms<=?",
            (symbol, start_ms, end_ms),
        ).fetchone()
        return float(row[0] or 0.0)

    def replace_positions(self, rows: list[dict]):
        columns = [
            "symbol", "side", "entry_price", "mark_price", "qty", "qty_closed", "leverage",
            "stop_loss", "tp1", "tp2", "tp3", "trailing_price", "unrealized_pnl",
            "unrealized_pnl_pct", "r_multiple", "position_value", "cum_realised_pnl",
            "opened_ts", "strategy_id", "exit_state", "tp1_done", "tp2_done", "tp3_done",
            "signal_json", "updated_ts",
        ]
        sql = f"INSERT INTO positions_live ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})"
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                self._conn.execute("DELETE FROM positions_live")
                for row in rows:
                    self._conn.execute(sql, [row.get(column) for column in columns])
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def list_positions(self):
        rows = self._conn.execute("SELECT * FROM positions_live ORDER BY symbol").fetchall()
        return [dict(row) for row in rows]

    def insert_equity(self, row):
        with self._lock:
            self._conn.execute(
                "INSERT INTO equity_snapshots (ts,equity,wallet_balance,available_balance,unrealized_pnl,open_positions) "
                "VALUES (?,?,?,?,?,?)",
                (
                    row.get("ts", time.time()), row.get("equity"), row.get("wallet_balance"),
                    row.get("available_balance"), row.get("unrealized_pnl"), row.get("open_positions"),
                ),
            )
            self._conn.commit()

    def list_equity(self, start_ts, end_ts, limit=5000):
        rows = self._conn.execute(
            "SELECT * FROM equity_snapshots WHERE ts>=? AND ts<=? ORDER BY id",
            (start_ts, end_ts),
        ).fetchall()
        values = [dict(row) for row in rows]
        if len(values) > limit > 0:
            step = max(1, len(values) // limit)
            values = values[::step][:limit]
        return values

    def latest_equity(self):
        row = self._conn.execute("SELECT * FROM equity_snapshots ORDER BY ts DESC, id DESC LIMIT 1").fetchone()
        return self._row(row)

    def insert_event(self, ts, level, event_type, message, symbol=None, strategy_id=None, metadata=None):
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO events (ts,level,event_type,symbol,strategy_id,message,metadata_json) VALUES (?,?,?,?,?,?,?)",
                (ts, level, event_type, symbol, strategy_id, message, self._json(metadata)),
            )
            self._conn.commit()
            return cursor.lastrowid

    def list_events(self, filters=None, limit=100, offset=0):
        filters = filters or {}
        clauses, params = [], []
        for field in ("level", "event_type", "symbol"):
            if filters.get(field) is not None:
                clauses.append(f"{field}=?")
                params.append(filters[field])
        for field, op in (("start_ts", ">="), ("end_ts", "<=")):
            if filters.get(field) is not None:
                clauses.append(f"ts {op} ?")
                params.append(filters[field])
        if filters.get("since_id") is not None:
            clauses.append("id > ?")
            params.append(filters["since_id"])
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        total = self._conn.execute(f"SELECT COUNT(*) FROM events{where}", params).fetchone()[0]
        rows = self._conn.execute(
            f"SELECT * FROM events{where} ORDER BY id DESC LIMIT ? OFFSET ?",
            [*params, int(limit), int(offset)],
        ).fetchall()
        return [dict(row) for row in rows], int(total)

    def distinct_event_types(self):
        rows = self._conn.execute(
            "SELECT DISTINCT event_type FROM events WHERE event_type IS NOT NULL ORDER BY event_type"
        ).fetchall()
        return [row[0] for row in rows]

    def get_setting(self, key, default=None):
        row = self._conn.execute("SELECT value_json FROM settings WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            return default

    def set_setting(self, key, value):
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO settings (key,value_json,updated_ts) VALUES (?,?,?)",
                (key, self._json(value), time.time()),
            )
            self._conn.commit()

    def create_session(self, token_hash, created_ts, expires_ts, user):
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO sessions (token_hash,created_ts,expires_ts,user) VALUES (?,?,?,?)",
                (token_hash, created_ts, expires_ts, user),
            )
            self._conn.commit()

    def get_session(self, token_hash, now=None):
        now = time.time() if now is None else now
        row = self._conn.execute(
            "SELECT token_hash,created_ts,expires_ts,user FROM sessions WHERE token_hash=?",
            (token_hash,),
        ).fetchone()
        if row is None or float(row["expires_ts"] or 0) <= now:
            if row is not None:
                self.delete_session(token_hash)
            return None
        result = dict(row)
        if float(result["expires_ts"]) - now < 6 * 3600:
            result["expires_ts"] = now + 12 * 3600
            with self._lock:
                self._conn.execute(
                    "UPDATE sessions SET expires_ts=? WHERE token_hash=?",
                    (result["expires_ts"], token_hash),
                )
                self._conn.commit()
        return result

    def delete_session(self, token_hash):
        with self._lock:
            self._conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
            self._conn.commit()

    def delete_expired_sessions(self, now=None):
        now = time.time() if now is None else now
        with self._lock:
            cursor = self._conn.execute("DELETE FROM sessions WHERE expires_ts<=?", (now,))
            self._conn.commit()
            return cursor.rowcount

    def write_heartbeat(self, fields: dict):
        columns = [
            "ts", "pid", "started_ts", "cycle_ms", "signals_generated", "executed_orders",
            "active_positions", "equity", "bybit_ok", "bybit_last_ok_ts", "bybit_last_error",
            "paused", "trading_enabled", "strategy_id", "config_path", "extra_json",
        ]
        row = dict(fields)
        extras = row.pop("extra_json", None)
        if extras is None:
            known = set(columns)
            extra_values = {key: value for key, value in row.items() if key not in known}
            extras = extra_values or None
        values = [self._json(extras) if column == "extra_json" else row.get(column) for column in columns]
        with self._lock:
            self._conn.execute(
                f"INSERT OR REPLACE INTO bot_heartbeat (id,{', '.join(columns)}) "
                f"VALUES (1,{', '.join('?' for _ in columns)})",
                values,
            )
            self._conn.commit()

    def read_heartbeat(self):
        row = self._conn.execute("SELECT * FROM bot_heartbeat WHERE id=1").fetchone()
        return self._row(row)

    def prune(self, events_keep_days=30, signals_keep_days=30, equity_keep_days=365):
        now = time.time()
        with self._lock:
            self._conn.execute("DELETE FROM events WHERE ts < ?", (now - events_keep_days * 86400,))
            self._conn.execute("DELETE FROM signals WHERE ts < ?", (now - signals_keep_days * 86400,))
            self._conn.execute(
                "DELETE FROM equity_snapshots WHERE ts < ?",
                (now - equity_keep_days * 86400,),
            )
            self._conn.commit()
