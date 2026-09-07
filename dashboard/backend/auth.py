from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Annotated

from fastapi import Cookie, HTTPException, Request, status

from dashboard.backend.settings import Settings
from dashboard.store import Store


COOKIE_NAME = "dash_session"
SESSION_TTL = 12 * 3600


class AuthManager:
    def __init__(self, store: Store, settings: Settings):
        self.store = store
        self.settings = settings
        salt = hashlib.sha256(settings.dashboard_secret.encode("utf-8")).digest()[:16]
        self._salt = salt
        self._password_hash = (
            hashlib.pbkdf2_hmac(
                "sha256",
                (settings.dashboard_password or "").encode("utf-8"),
                salt,
                200_000,
            )
            if settings.dashboard_password is not None
            else None
        )
        self._failures = {}

    def _hash_password(self, password: str):
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), self._salt, 200_000)

    def _ip(self, request: Request):
        return request.client.host if request.client else "unknown"

    def _rate_locked(self, ip: str):
        failure = self._failures.get(ip)
        return bool(failure and failure[1] > time.time())

    def login(self, request: Request, username: str, password: str):
        ip = self._ip(request)
        if self.settings.dashboard_password is None:
            self.store.insert_event(
                time.time(), "WARNING", "AUTH_FAILED", "dashboard password is not configured",
                metadata={"ip": ip},
            )
            raise HTTPException(status_code=503, detail="DASHBOARD_PASSWORD not set")
        if self._rate_locked(ip):
            raise HTTPException(status_code=429, detail="login temporarily locked")
        valid = (
            hmac.compare_digest(username, self.settings.dashboard_username)
            and self._password_hash is not None
            and hmac.compare_digest(self._hash_password(password), self._password_hash)
        )
        if not valid:
            count, _ = self._failures.get(ip, (0, 0))
            count += 1
            lock_until = time.time() + 60 if count >= 5 else 0
            self._failures[ip] = (count, lock_until)
            self.store.insert_event(
                time.time(), "WARNING", "AUTH_FAILED", "dashboard login failed",
                metadata={"ip": ip},
            )
            if lock_until:
                raise HTTPException(status_code=429, detail="login temporarily locked")
            raise HTTPException(status_code=401, detail="invalid credentials")
        self._failures.pop(ip, None)
        token = secrets.token_urlsafe(32)
        now = time.time()
        self.store.create_session(
            hashlib.sha256(token.encode("utf-8")).hexdigest(),
            now,
            now + SESSION_TTL,
            username,
        )
        self.store.insert_event(
            now, "INFO", "AUTH_LOGIN", "dashboard login succeeded", metadata={"ip": ip, "user": username},
        )
        return token

    def user_from_token(self, token: str | None):
        if not token:
            return None
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        session = self.store.get_session(digest)
        return session

    def logout(self, token: str | None):
        if token:
            self.store.delete_session(hashlib.sha256(token.encode("utf-8")).hexdigest())


def get_auth(request: Request) -> AuthManager:
    return request.app.state.auth


async def require_user(
    request: Request,
    dash_session: Annotated[str | None, Cookie()] = None,
):
    auth = get_auth(request)
    session = auth.user_from_token(dash_session)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    request.state.user = session["user"]
    return session["user"]
