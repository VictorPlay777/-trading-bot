"""
Runtime resilience utilities: crash snapshots, heartbeat, and health metrics.
"""
from __future__ import annotations

import json
import os
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None


class StateStore:
    """Simple JSON state persistence with atomic writes."""

    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def save(self, payload: Dict[str, Any]) -> None:
        temp_path = f"{self.path}.tmp"
        with self._lock:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, self.path)

    def load(self) -> Optional[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return None
        with self._lock:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)


class CrashSnapshotter:
    """Persists structured snapshots for post-mortem crash analysis."""

    def __init__(self, crash_dir: str = "crash_dumps"):
        self.crash_dir = crash_dir
        Path(crash_dir).mkdir(parents=True, exist_ok=True)

    def dump(self, reason: str, context: Dict[str, Any], exc: Exception | None = None) -> str:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        path = os.path.join(self.crash_dir, f"crash_{ts}.json")
        payload: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "reason": reason,
            "context": context,
        }
        if exc is not None:
            payload["exception"] = repr(exc)
            payload["traceback"] = traceback.format_exc()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return path


class RuntimeMonitor:
    """Collects lightweight process and loop health metrics."""

    def __init__(self):
        self.started_at = time.time()
        self.last_heartbeat_ts = time.time()
        self.event_loop_lag_ms = 0.0
        self.reconnect_count = 0
        self.dropped_messages = 0
        self.api_latency_ms = 0.0
        self.last_cycle_latency_ms = 0.0

    def heartbeat(self) -> None:
        now = time.time()
        expected = self.last_heartbeat_ts + 1.0
        self.event_loop_lag_ms = max(0.0, (now - expected) * 1000.0)
        self.last_heartbeat_ts = now

    def record_cycle_latency(self, latency_ms: float) -> None:
        self.last_cycle_latency_ms = latency_ms

    def record_api_latency(self, latency_ms: float) -> None:
        self.api_latency_ms = latency_ms

    def record_reconnect(self) -> None:
        self.reconnect_count += 1

    def record_dropped_message(self) -> None:
        self.dropped_messages += 1

    def snapshot(self) -> Dict[str, Any]:
        proc_data: Dict[str, Any] = {
            "uptime_sec": int(time.time() - self.started_at),
            "heartbeat_age_sec": round(time.time() - self.last_heartbeat_ts, 3),
            "event_loop_lag_ms": round(self.event_loop_lag_ms, 3),
            "api_latency_ms": round(self.api_latency_ms, 3),
            "cycle_latency_ms": round(self.last_cycle_latency_ms, 3),
            "reconnect_count": self.reconnect_count,
            "dropped_messages": self.dropped_messages,
        }
        if psutil:
            p = psutil.Process()
            proc_data.update(
                {
                    "ram_mb": round(p.memory_info().rss / (1024 * 1024), 2),
                    "cpu_pct": p.cpu_percent(interval=0.0),
                    "open_fds_or_handles": getattr(p, "num_fds", p.num_handles)() if hasattr(p, "num_fds") or hasattr(p, "num_handles") else None,
                    "threads": p.num_threads(),
                    "connections": len(p.connections(kind="inet")),
                }
            )
        return proc_data
