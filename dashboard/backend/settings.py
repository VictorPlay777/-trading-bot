from __future__ import annotations

import os
import secrets
import sys
from dataclasses import dataclass

from loguru import logger


@dataclass
class Settings:
    dashboard_password: str | None
    dashboard_username: str
    dashboard_secret: str
    dashboard_db_path: str | None
    bot_config_path: str
    bot_python: str
    bot_log_path: str
    bot_auto_restart: bool
    dashboard_cookie_secure: bool

    @classmethod
    def from_env(cls):
        password = os.getenv("DASHBOARD_PASSWORD")
        secret = os.getenv("DASHBOARD_SECRET")
        if not secret:
            secret = secrets.token_urlsafe(32)
            logger.warning("DASHBOARD_SECRET not set; dashboard sessions will not survive restart")
        if not password:
            logger.error("DASHBOARD_PASSWORD not set; dashboard login is disabled")
        return cls(
            dashboard_password=password,
            dashboard_username=os.getenv("DASHBOARD_USERNAME", "admin"),
            dashboard_secret=secret,
            dashboard_db_path=os.getenv("DASHBOARD_DB_PATH"),
            bot_config_path=os.getenv("BOT_CONFIG_PATH", "config_scanner.yaml"),
            bot_python=os.getenv("BOT_PYTHON", sys.executable),
            bot_log_path=os.getenv("BOT_LOG_PATH", "logs/bot_stdout.log"),
            bot_auto_restart=os.getenv("BOT_AUTO_RESTART", "true").lower() not in {"0", "false", "no"},
            dashboard_cookie_secure=os.getenv("DASHBOARD_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"},
        )


settings = Settings.from_env()
