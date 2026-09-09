from __future__ import annotations

import re
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator

from dashboard.bot_bridge import DEFAULT_RISK
from dashboard.backend.routes.common import User


router = APIRouter(prefix="/api", tags=["risk"])
SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,20}USDT$")


class RiskBody(BaseModel):
    risk_per_trade_pct: float = Field(ge=0, le=100)
    max_open_positions: int = Field(ge=0, le=999)
    max_daily_loss_pct: float = Field(ge=0, le=100)
    max_daily_loss_usd: float = Field(ge=0)
    max_drawdown_pct: float = Field(ge=0, le=100)
    max_position_notional_usdt: float = Field(ge=0)
    max_leverage: int = Field(ge=1, le=100)
    long_enabled: bool
    short_enabled: bool
    allowed_symbols: list[str]
    kill_switch_enabled: bool
    kill_switch_close_positions: bool
    kill_switch_auto_reset_daily: bool

    @field_validator("allowed_symbols")
    @classmethod
    def symbols_valid(cls, values):
        if any(not SYMBOL_RE.fullmatch(value) for value in values):
            raise ValueError("allowed_symbols must match ^[A-Z0-9]{2,20}USDT$")
        return values


class ControlBody(BaseModel):
    trading_enabled: bool


def _schema():
    return [
        {"key": "risk_per_trade_pct", "type": "percent", "min": 0, "max": 100, "label": "Risk per trade", "dangerous": True},
        {"key": "max_open_positions", "type": "integer", "min": 0, "max": 999, "label": "Max open positions", "dangerous": True},
        {"key": "max_daily_loss_pct", "type": "percent", "min": 0, "max": 100, "label": "Max daily loss", "dangerous": True},
        {"key": "max_daily_loss_usd", "type": "usd", "min": 0, "max": None, "label": "Max daily loss USD", "dangerous": True},
        {"key": "max_drawdown_pct", "type": "percent", "min": 0, "max": 100, "label": "Max drawdown", "dangerous": True},
        {"key": "max_position_notional_usdt", "type": "usd", "min": 0, "max": None, "label": "Max position notional", "dangerous": True},
        {"key": "max_leverage", "type": "integer", "min": 1, "max": 100, "label": "Max leverage", "dangerous": True},
    ]


@router.get("/risk")
async def get_risk(request: Request, _user: User):
    values = dict(DEFAULT_RISK)
    values.update(request.app.state.store.get_setting("risk", {}) or {})
    return {**values, "schema": _schema()}


@router.put("/risk")
async def put_risk(body: RiskBody, request: Request, _user: User):
    old = dict(DEFAULT_RISK)
    old.update(request.app.state.store.get_setting("risk", {}) or {})
    new = body.model_dump()
    diff = {key: {"old": old.get(key), "new": value} for key, value in new.items() if old.get(key) != value}
    request.app.state.store.set_setting("risk", new)
    request.app.state.store.insert_event(time.time(), "WARNING", "RISK_SETTINGS_CHANGED", "risk settings changed", metadata={"diff": diff})
    return {**new, "schema": _schema()}


@router.get("/control")
async def get_control(request: Request, _user: User):
    from dashboard.bot_bridge import DEFAULT_CONTROL
    values = dict(DEFAULT_CONTROL)
    values.update(request.app.state.store.get_setting("control", {}) or {})
    return values


@router.put("/control")
async def put_control(body: ControlBody, request: Request, _user: User):
    control = dict(request.app.state.store.get_setting("control", {}) or {})
    control["trading_enabled"] = body.trading_enabled
    request.app.state.store.set_setting("control", control)
    event_type = "TRADING_ENABLED" if body.trading_enabled else "TRADING_DISABLED"
    request.app.state.store.insert_event(time.time(), "WARNING", event_type, event_type.lower())
    return control
