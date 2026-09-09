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


def login(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "secret"})
    assert response.status_code == 200
    return {"X-Requested-With": "dashboard"}


def test_auth_and_csrf(client):
    assert client.get("/api/status").status_code == 401
    for _ in range(4):
        assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 429
    assert client.post("/api/bot/pause").status_code == 403


def test_login_cookie_and_logout(client):
    headers = login(client)
    assert client.get("/api/auth/me").json()["user"] == "admin"
    assert client.post("/api/bot/pause", headers=headers).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/status").status_code == 401
