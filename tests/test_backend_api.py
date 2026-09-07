from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dashboard.backend.app import app
from dashboard.backend.settings import settings


@pytest.fixture
def client(tmp_path):
    settings.dashboard_password = "secret"
    settings.dashboard_secret = "test-secret"
    settings.dashboard_db_path = str(tmp_path / "dashboard.db")
    settings.bot_auto_restart = False
    with TestClient(app) as value:
        yield value


def auth(client):
    assert client.post("/api/auth/login", json={"username": "admin", "password": "secret"}).status_code == 200
    return {"X-Requested-With": "dashboard"}


def test_risk_validation_and_trade_filters(client):
    headers = auth(client)
    assert client.put("/api/risk", headers=headers, json={
        "risk_per_trade_pct": 150, "max_open_positions": 1,
        "max_daily_loss_pct": 1, "max_daily_loss_usd": 1,
        "max_drawdown_pct": 1, "max_position_notional_usdt": 1,
        "max_leverage": 1, "long_enabled": True, "short_enabled": True,
        "allowed_symbols": ["BTCUSDT"], "kill_switch_enabled": True,
        "kill_switch_close_positions": False, "kill_switch_auto_reset_daily": True,
    }).status_code == 422
    body = {
        "risk_per_trade_pct": 1, "max_open_positions": 1,
        "max_daily_loss_pct": 1, "max_daily_loss_usd": 1,
        "max_drawdown_pct": 1, "max_position_notional_usdt": 1,
        "max_leverage": 1, "long_enabled": True, "short_enabled": True,
        "allowed_symbols": ["BTCUSDT"], "kill_switch_enabled": True,
        "kill_switch_close_positions": False, "kill_switch_auto_reset_daily": True,
    }
    response = client.put("/api/risk", headers=headers, json=body)
    assert response.status_code == 200
    assert client.get("/api/events", headers=headers).json()["items"][0]["event_type"] == "RISK_SETTINGS_CHANGED"
    assert client.get("/api/trades?limit=1", headers=headers).json()["total"] == 0


def test_strategy_settings_and_sltp_reject_when_stopped(client):
    headers = auth(client)
    strategy_id = client.get("/api/strategies", headers=headers).json()[0]["strategy_id"]
    response = client.put(
        f"/api/strategies/{strategy_id}/settings",
        headers=headers,
        json={"overrides": {"does_not_exist": 1}, "restart": False},
    )
    assert response.status_code == 422
    assert client.post("/api/positions/BTCUSDT/sltp", headers=headers, json={"stop_loss": 1}).status_code == 409


def test_emergency_confirmation(client):
    headers = auth(client)
    assert client.post(
        "/api/bot/emergency-stop", headers=headers,
        json={"confirm_phrase": "wrong", "close_positions": False},
    ).status_code == 400
