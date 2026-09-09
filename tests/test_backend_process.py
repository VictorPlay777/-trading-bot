from __future__ import annotations

from pathlib import Path

from dashboard.backend.process_manager import ProcessManager
from dashboard.backend.settings import Settings
from dashboard.store import Store


class FakeChild:
    pid = 123

    def __init__(self):
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if not self.terminated and not self.killed else 0

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return 0


def test_emergency_flags_and_reset(tmp_path):
    settings = Settings(
        dashboard_password="secret", dashboard_username="admin", dashboard_secret="secret",
        dashboard_db_path=str(tmp_path / "db"), bot_config_path="config_scanner.yaml",
        bot_python="python", bot_log_path=str(tmp_path / "bot.log"),
        bot_auto_restart=False, dashboard_cookie_secure=False,
    )
    store = Store(str(tmp_path / "db"))
    manager = ProcessManager(store, settings, repo_root=Path.cwd())
    child = FakeChild()
    manager.child = child
    manager.child_pid = child.pid

    import asyncio
    asyncio.run(manager.emergency_stop())
    assert child.terminated
    assert store.get_setting("control")["emergency_stop"] is True
    asyncio.run(manager.reset_emergency())
    assert store.get_setting("control")["emergency_stop"] is False
