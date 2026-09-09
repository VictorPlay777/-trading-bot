from __future__ import annotations

import asyncio
import inspect
import os
import signal
import subprocess
import time
from pathlib import Path

from loguru import logger

from dashboard.backend.settings import Settings
from dashboard.store import Store
from dashboard.bot_bridge import DEFAULT_CONTROL

try:
    import psutil
except Exception:
    psutil = None


class ProcessManager:
    def __init__(self, store: Store, settings: Settings, exchange_client=None, repo_root: Path | None = None):
        self.store = store
        self.settings = settings
        self.exchange_client = exchange_client
        self.repo_root = repo_root or Path(__file__).resolve().parents[2]
        self.child = None
        self.child_pid = None
        self.last_exit_code = None
        self.last_exit_ts = None
        self._user_stopped = False
        self._restart_backoff = 5.0
        self._next_restart_ts = 0.0
        self._running_since = None
        self._last_session_cleanup = 0.0

    def _control(self):
        control = dict(DEFAULT_CONTROL)
        control.update(self.store.get_setting("control", {}) or {})
        return control

    def _set_control(self, updates):
        control = self._control()
        control.update(updates)
        self.store.set_setting("control", control)
        return control

    def _event(self, level, event_type, message, metadata=None):
        return self.store.insert_event(
            time.time(), level, event_type, message, strategy_id=None, metadata=metadata
        )

    def is_running(self):
        return self.child is not None and self.child.poll() is None

    def _cmdline(self, pid):
        try:
            if psutil is not None:
                return psutil.Process(pid).cmdline()
            result = subprocess.run(
                ["ps", "-o", "command=", "-p", str(pid)],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            return result.stdout.strip().split()
        except Exception:
            return []

    def _processes(self):
        if psutil is not None:
            try:
                for process in psutil.process_iter(["pid", "cmdline"]):
                    yield process.info["pid"], process.info.get("cmdline") or []
                return
            except Exception:
                pass
        try:
            output = subprocess.run(
                ["pgrep", "-af", "selective_ml_bot.py"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            ).stdout
            for line in output.splitlines():
                parts = line.split(None, 1)
                if len(parts) == 2:
                    yield int(parts[0]), parts[1].split()
        except Exception:
            return

    def _is_bot_cmdline(self, cmdline):
        # interpreter followed by the bot script as its own argument
        # (not e.g. `grep selective_ml_bot.py` or an editor holding the file)
        if not cmdline or "python" not in Path(cmdline[0]).name:
            return False
        for part in cmdline[1:]:
            if Path(part).name == "selective_ml_bot.py":
                script = Path(part)
                if script.is_absolute():
                    return script.resolve() == (self.repo_root / "selective_ml_bot.py").resolve()
                return True
        return False

    def _same_repo(self, pid):
        if psutil is None:
            return True
        try:
            return Path(psutil.Process(pid).cwd()).resolve() == self.repo_root.resolve()
        except Exception:
            return False

    def external_pid(self):
        for pid, cmdline in self._processes():
            if self.child_pid and pid == self.child_pid:
                continue
            if self._is_bot_cmdline(cmdline) and self._same_repo(pid):
                return pid
        return None

    def supervisor_pid(self):
        for pid, cmdline in self._processes():
            if any("run_selective_ml_forever" in part for part in cmdline):
                return pid
        return None

    async def start(self):
        if self.is_running():
            return {"ok": False, "error": "bot already running", "pid": self.child_pid}
        control = self._control()
        if control.get("emergency_stop"):
            return {"ok": False, "error": "emergency stop active"}
        external = self.external_pid()
        if external is not None:
            return {"ok": False, "error": f"bot already running outside dashboard (pid {external})"}
        config_path = Path(self.settings.bot_config_path)
        config_arg = str(config_path)
        log_path = Path(self.settings.bot_log_path)
        if not log_path.is_absolute():
            log_path = self.repo_root / log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._set_control({"paused": False})
        self.store.write_heartbeat({"ts": 0})
        handle = log_path.open("a", encoding="utf-8")
        try:
            self.child = subprocess.Popen(
                [self.settings.bot_python, "selective_ml_bot.py", "--config", config_arg],
                cwd=str(self.repo_root),
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except Exception:
            handle.close()
            self.child = None
            raise
        handle.close()
        self.child_pid = self.child.pid
        self.last_exit_code = None
        self._user_stopped = False
        self._running_since = time.time()
        self._restart_backoff = 5.0
        self._event("INFO", "BOT_START_REQUESTED", "bot start requested", {"pid": self.child_pid})
        return {"ok": True, "pid": self.child_pid}

    async def _terminate_child(self, force=False):
        child = self.child
        if child is None:
            return
        try:
            if child.poll() is None:
                (child.kill if force else child.terminate)()
            if not force:
                try:
                    await asyncio.to_thread(child.wait, 30)
                except subprocess.TimeoutExpired:
                    child.kill()
                    await asyncio.to_thread(child.wait, 5)
            else:
                await asyncio.to_thread(child.wait, 5)
        except Exception as exc:
            logger.warning(f"dashboard process termination failed: {exc}")
        self.last_exit_code = child.poll()
        self.child = None
        self.child_pid = None

    async def stop(self, reason="user", allow_external=False):
        self._user_stopped = True
        if self.is_running():
            pid = self.child_pid
            self._event("INFO", "BOT_STOP_REQUESTED", f"bot stop requested: {reason}", {"pid": pid})
            await self._terminate_child()
            return {"ok": True, "stopped": True, "pid": pid}
        external = self.external_pid()
        if external is not None:
            if not allow_external:
                return {"ok": False, "error": "external bot requires allow_external=true"}
            supervisor = self.supervisor_pid()
            if supervisor is not None:
                return {"ok": False, "error": f"supervisor detected (pid {supervisor}): stop it first"}
            try:
                os.kill(external, signal.SIGTERM)
                self._event("WARNING", "BOT_STOP_REQUESTED", "external bot stop requested", {"pid": external})
                return {"ok": True, "stopped": True, "pid": external, "managed": False}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}
        return {"ok": False, "error": "bot not running"}

    async def restart(self):
        await self.stop("restart")
        return await self.start()

    async def pause(self):
        self._set_control({"paused": True})
        self._event("INFO", "BOT_PAUSED", "bot paused")
        return {"ok": True}

    async def resume(self):
        self._set_control({"paused": False})
        self._event("INFO", "BOT_RESUMED", "bot resumed")
        return {"ok": True}

    async def emergency_stop(self, close_positions=False):
        self._set_control({"emergency_stop": True, "trading_enabled": False, "paused": True})
        self._event("CRITICAL", "EMERGENCY_STOP", "emergency stop requested")
        result = {"ok": True, "closed": [], "errors": []}
        if self.is_running():
            await self._terminate_child()
        if close_positions and self.exchange_client is not None:
            response = await self._exchange_call("positions")
            rows = ((response or {}).get("result") or {}).get("list") or []
            for row in rows:
                try:
                    qty = float(row.get("size", 0) or 0)
                    if qty <= 0:
                        continue
                    side = "long" if row.get("side") == "Buy" else "short"
                    close_result = await self._exchange_call("close_position", row["symbol"], side, qty)
                    if close_result is None or int(close_result.get("retCode", -1)) != 0:
                        result["errors"].append(row.get("symbol"))
                        self._event("ERROR", "ORDER_FAILED", "forced position close failed", {"symbol": row.get("symbol")})
                    else:
                        result["closed"].append(row.get("symbol"))
                        self._event("WARNING", "POSITION_FORCE_CLOSED", "position force closed", {"symbol": row.get("symbol")})
                except Exception as exc:
                    result["errors"].append(row.get("symbol"))
                    self._event("ERROR", "ORDER_FAILED", str(exc), {"symbol": row.get("symbol")})
        return result

    async def _exchange_call(self, method, *args):
        result = await asyncio.to_thread(getattr(self.exchange_client, method), *args)
        if inspect.isawaitable(result):
            return await result
        return result

    async def reset_emergency(self):
        self._set_control({"emergency_stop": False, "trading_enabled": True, "paused": False})
        self._event("INFO", "EMERGENCY_RESET", "emergency stop reset")
        return {"ok": True}

    async def poll(self):
        if self.child is None:
            return
        code = self.child.poll()
        if code is None:
            if self._running_since and time.time() - self._running_since > 300:
                self._restart_backoff = 5.0
            return
        self.last_exit_code = code
        self.last_exit_ts = time.time()
        user_stopped = self._user_stopped
        self.child = None
        self.child_pid = None
        level = "INFO" if code == 0 or user_stopped else "ERROR"
        self._event(level, "BOT_EXITED", f"bot exited with code {code}", {"code": code})
        if self.settings.bot_auto_restart and not user_stopped and not self._control().get("emergency_stop"):
            self._next_restart_ts = time.time() + self._restart_backoff
            self._restart_backoff = min(self._restart_backoff * 2, 60.0)

    async def maintenance(self):
        await self.poll()
        if self.child is None and self.settings.bot_auto_restart and self._next_restart_ts:
            if time.time() >= self._next_restart_ts and not self._user_stopped and not self._control().get("emergency_stop"):
                self._next_restart_ts = 0
                try:
                    await self.start()
                except Exception as exc:
                    logger.error(f"dashboard auto-restart failed: {exc}")
        if time.time() - self._last_session_cleanup >= 600:
            self.store.delete_expired_sessions()
            self._last_session_cleanup = time.time()

    async def run(self):
        last_prune = 0.0
        while True:
            try:
                await self.maintenance()
            except Exception as exc:
                logger.error(f"dashboard process manager loop failed: {exc}")
            if time.time() - last_prune >= 86400:
                try:
                    self.store.prune()
                except Exception as exc:
                    logger.error(f"dashboard maintenance prune failed: {exc}")
                last_prune = time.time()
            await asyncio.sleep(2)
