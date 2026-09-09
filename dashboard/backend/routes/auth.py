from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Request, Response
from pydantic import BaseModel

from dashboard.backend.auth import COOKIE_NAME, require_user


router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response):
    token = request.app.state.auth.login(request, body.username, body.password)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=12 * 3600,
        httponly=True,
        samesite="strict",
        secure=request.app.state.settings.dashboard_cookie_secure,
        path="/",
    )
    return {"ok": True, "user": body.username}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    dash_session: str | None = Cookie(default=None),
    _user=Depends(require_user),
):
    request.app.state.auth.logout(dash_session)
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
async def me(request: Request, _user=Depends(require_user)):
    return {"user": _user}
