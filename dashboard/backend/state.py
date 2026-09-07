from __future__ import annotations

import time

from dashboard.bot_bridge import DEFAULT_CONTROL, DEFAULT_RISK


def _merged(store, key, defaults):
    value = dict(defaults)
    value.update(store.get_setting(key, {}) or {})
    return value


def compute_status(store, pm, exchange_client) -> dict:
    now = time.time()
    external_pid = pm.external_pid()
    managed = pm.is_running()
    process_running = managed or external_pid is not None
    heartbeat = store.read_heartbeat()
    heartbeat_ts = heartbeat.get("ts") if heartbeat else None
    heartbeat_age = now - float(heartbeat_ts) if heartbeat_ts else None
    control = _merged(store, "control", DEFAULT_CONTROL)
    risk = _merged(store, "risk", DEFAULT_RISK)
    warnings = []
    started_ago = now - pm._running_since if managed and pm._running_since else None
    booting = started_ago is not None and started_ago < 180
    stale = heartbeat_age is None or heartbeat_age > 45
    if control.get("emergency_stop"):
        state = "EMERGENCY_STOP"
    elif not process_running:
        state = "STOPPED"
        if pm.last_exit_code not in (None, 0) and not getattr(pm, "_user_stopped", False):
            state = "ERROR"
    elif stale and booting:
        state = "STARTING"
    elif stale:
        state = "ERROR"
        warnings.append("heartbeat stale")
    elif heartbeat.get("bybit_ok") == 0:
        state = "CONNECTION_ERROR"
    elif control.get("kill_switch_triggered"):
        state = "KILL_SWITCH"
    elif control.get("paused") or not control.get("trading_enabled", True):
        state = "PAUSED"
    else:
        state = "RUNNING"
    if external_pid is not None:
        warnings.append(f"external bot process detected (pid {external_pid})")
    if not getattr(pm.settings, "dashboard_password", None):
        warnings.append("DASHBOARD_PASSWORD unset")
    kill_state = store.get_setting("kill_switch_state", {}) or {}
    if control.get("kill_switch_triggered") and control.get("kill_switch_reason"):
        warnings.append(str(control["kill_switch_reason"]))
    bybit_connected = False
    if process_running and heartbeat_age is not None and heartbeat_age <= 45:
        bybit_connected = bool(heartbeat.get("bybit_ok"))
    elif exchange_client.last_ok_ts is not None:
        bybit_connected = now - exchange_client.last_ok_ts <= 60
    return {
        "status": state,
        "state": state,
        "substatus": "heartbeat_stale" if process_running and stale else None,
        "process_running": process_running,
        "pid": pm.child_pid or external_pid,
        "managed": managed,
        "strategy_id": heartbeat.get("strategy_id") if heartbeat else None,
        "config_path": heartbeat.get("config_path") if heartbeat else None,
        "last_heartbeat_ts": heartbeat_ts,
        "heartbeat_age_sec": heartbeat_age,
        "cycle_ms": heartbeat.get("cycle_ms") if heartbeat else None,
        "uptime_sec": (
            now - float(heartbeat.get("started_ts"))
            if process_running and heartbeat and heartbeat.get("started_ts")
            else None
        ),
        "bybit": {
            "connected": bybit_connected,
            "last_ok_ts": heartbeat.get("bybit_last_ok_ts") if heartbeat else exchange_client.last_ok_ts,
            "last_error": heartbeat.get("bybit_last_error") if heartbeat else exchange_client.last_error,
        },
        "control": control,
        "risk": risk,
        "kill_switch": kill_state,
        "warnings": warnings,
        "last_exit_code": pm.last_exit_code,
    }
