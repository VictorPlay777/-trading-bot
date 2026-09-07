from __future__ import annotations

import time

from dashboard.backend.state import compute_status
from dashboard.store import Store


class FakePM:
    def __init__(self):
        self.running = False
        self.external = None
        self.child_pid = None
        self.last_exit_code = None
        self._user_stopped = False
        self.settings = type("Settings", (), {"dashboard_password": "secret"})()

    def is_running(self):
        return self.running

    def external_pid(self):
        return self.external


class FakeExchange:
    last_ok_ts = None
    last_error = None


def test_status_state_machine(tmp_path):
    db = Store(str(tmp_path / "db"))
    pm = FakePM()
    exchange = FakeExchange()
    assert compute_status(db, pm, exchange)["status"] == "STOPPED"
    pm.running = True
    db.write_heartbeat({"ts": time.time(), "started_ts": time.time(), "bybit_ok": 1})
    assert compute_status(db, pm, exchange)["status"] == "RUNNING"
    control = {"paused": True}
    db.set_setting("control", control)
    assert compute_status(db, pm, exchange)["status"] == "PAUSED"
    db.set_setting("control", {})
    db.write_heartbeat({"ts": time.time() - 60, "started_ts": time.time() - 60, "bybit_ok": 1})
    assert compute_status(db, pm, exchange)["status"] == "ERROR"
    db.write_heartbeat({"ts": time.time(), "started_ts": time.time(), "bybit_ok": 0})
    assert compute_status(db, pm, exchange)["status"] == "CONNECTION_ERROR"
    db.set_setting("control", {"emergency_stop": True})
    assert compute_status(db, pm, exchange)["status"] == "EMERGENCY_STOP"
    db.write_heartbeat({"ts": time.time(), "started_ts": time.time(), "bybit_ok": 1})
    db.set_setting("control", {"kill_switch_triggered": True, "emergency_stop": False})
    assert compute_status(db, pm, exchange)["status"] == "KILL_SWITCH"


def test_zero_heartbeat_is_unavailable(tmp_path):
    db = Store(str(tmp_path / "db"))
    pm = FakePM()
    exchange = FakeExchange()
    db.write_heartbeat({"ts": 0, "started_ts": 0, "bybit_ok": 1})
    result = compute_status(db, pm, exchange)
    assert result["last_heartbeat_ts"] is None
    assert result["heartbeat_age_sec"] is None
