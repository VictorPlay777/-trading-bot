from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from dashboard.backend.routes.common import User, manager, status


router = APIRouter(prefix="/api/bot", tags=["bot"])


class ExternalBody(BaseModel):
    allow_external: bool = False


class EmergencyBody(BaseModel):
    confirm_phrase: str
    close_positions: bool = False


class ConfirmBody(BaseModel):
    confirm: bool


@router.post("/start")
async def start(request: Request, _user: User):
    result = await manager(request).start()
    return {"result": result, "status": status(request)}


@router.post("/stop")
async def stop(body: ExternalBody, request: Request, _user: User):
    result = await manager(request).stop("user", body.allow_external)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result["error"])
    return {"result": result, "status": status(request)}


@router.post("/pause")
async def pause(request: Request, _user: User):
    return {"result": await manager(request).pause(), "status": status(request)}


@router.post("/resume")
async def resume(request: Request, _user: User):
    return {"result": await manager(request).resume(), "status": status(request)}


@router.post("/restart")
async def restart(request: Request, _user: User):
    result = await manager(request).restart()
    return {"result": result, "status": status(request)}


@router.post("/emergency-stop")
async def emergency_stop(body: EmergencyBody, request: Request, _user: User):
    if body.confirm_phrase != "EMERGENCY STOP":
        raise HTTPException(status_code=400, detail="invalid confirmation phrase")
    result = await manager(request).emergency_stop(body.close_positions)
    return {"result": result, "status": status(request)}


@router.post("/reset-emergency")
async def reset_emergency(body: ConfirmBody, request: Request, _user: User):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirmation required")
    return {"result": await manager(request).reset_emergency(), "status": status(request)}


@router.post("/kill-switch/reset")
async def reset_kill_switch(body: ConfirmBody, request: Request, _user: User):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirmation required")
    db = request.app.state.store
    control = dict(db.get_setting("control", {}) or {})
    control.update({"kill_switch_triggered": False, "kill_switch_reason": None})
    state = dict(db.get_setting("kill_switch_state", {}) or {})
    state.update({"triggered": False, "triggered_reason": None, "triggered_ts": None})
    db.set_setting("control", control)
    db.set_setting("kill_switch_state", state)
    db.insert_event(__import__("time").time(), "WARNING", "KILL_SWITCH_RESET", "kill switch reset")
    return {"ok": True, "status": status(request)}
