from __future__ import annotations

import math
import time
from dataclasses import fields

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from dashboard.backend.routes.common import User, all_trades
from dashboard.backend.stats import by_strategy, period_bounds
from dashboard.bot_bridge import DEFAULT_CONTROL
from selective_config import ProductionConfig


router = APIRouter(prefix="/api/strategies", tags=["strategies"])
DANGEROUS = {
    "sizing_mode", "base_notional_usdt", "risk_per_trade", "max_position_notional_usdt",
    "max_total_exposure_usdt", "max_concurrent_positions", "leverage_target",
    "force_leverage_1x", "invert_signals", "enable_kill_switch", "daily_max_drawdown",
    "max_daily_drawdown_usdt", "sl_atr_mult", "tp1_r", "tp2_r", "tp3_r", "prob_threshold_base",
}
SIGNED_FIELDS = {"min_ev", "ev_min_decision", "reversal_conf_threshold"}


class StrategySettingsBody(BaseModel):
    overrides: dict
    restart: bool = False


def active_id():
    return ProductionConfig().strategy_id


def _type_name(value):
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    return None


def _fields_for(strategy_id, db):
    if strategy_id != active_id():
        raise HTTPException(status_code=404, detail="strategy not found")
    config = ProductionConfig()
    overrides = db.get_setting(f"strategy_overrides:{strategy_id}", {}) or {}
    rows = []
    for field in fields(config):
        default = getattr(config, field.name)
        type_name = _type_name(default)
        if type_name is None:
            continue
        current = overrides.get(field.name, default)
        rows.append({
            "name": field.name, "type": type_name, "default": default,
            "current": current, "override": field.name in overrides,
            "dangerous": field.name in DANGEROUS,
        })
    return rows


@router.get("")
async def strategies(request: Request, _user: User):
    db = request.app.state.store
    strategy_metrics = by_strategy(all_trades(db))
    active = active_id()
    control = dict(DEFAULT_CONTROL)
    control.update(db.get_setting("control", {}) or {})
    today_start, _ = period_bounds("today")
    rows = []
    seen = {active, *strategy_metrics.keys()}
    for strategy_id in seen:
        positions = sum(1 for row in db.list_positions() if row.get("strategy_id") == strategy_id)
        rows.append({
            "strategy_id": strategy_id,
            "active": strategy_id == active,
            "enabled": control.get("trading_enabled", True) if strategy_id == active else False,
            "running": request.app.state.process_manager.is_running() and strategy_id == active,
            **strategy_metrics.get(strategy_id, {}),
            "trades_today": sum(
                1 for row in all_trades(db)
                if row.get("strategy_id") == strategy_id and float(row.get("closed_ts") or 0) >= today_start
            ),
            "open_positions": positions,
        })
    return rows


@router.get("/{strategy_id}/settings")
async def get_strategy_settings(strategy_id: str, request: Request, _user: User):
    return {"strategy_id": strategy_id, "fields": _fields_for(strategy_id, request.app.state.store), "applies_on": "restart"}


@router.put("/{strategy_id}/settings")
async def put_strategy_settings(strategy_id: str, body: StrategySettingsBody, request: Request, _user: User):
    fields_by_name = {row["name"]: row for row in _fields_for(strategy_id, request.app.state.store)}
    for key, value in body.overrides.items():
        if key not in fields_by_name:
            raise HTTPException(status_code=422, detail=f"unknown strategy setting: {key}")
        expected = fields_by_name[key]["type"]
        valid = (
            (expected == "bool" and type(value) is bool)
            or (expected == "int" and type(value) is int)
            or (expected == "float" and type(value) in (int, float))
            or (expected == "str" and isinstance(value, str))
        )
        if not valid or (isinstance(value, (int, float)) and not math.isfinite(value)):
            raise HTTPException(status_code=422, detail=f"invalid type for strategy setting: {key}")
        if isinstance(value, (int, float)) and key not in SIGNED_FIELDS and value < 0:
            raise HTTPException(status_code=422, detail=f"negative value not allowed: {key}")
    old = request.app.state.store.get_setting(f"strategy_overrides:{strategy_id}", {}) or {}
    request.app.state.store.set_setting(f"strategy_overrides:{strategy_id}", {**old, **body.overrides})
    diff = {key: {"old": old.get(key), "new": value} for key, value in body.overrides.items() if old.get(key) != value}
    request.app.state.store.insert_event(time.time(), "WARNING", "STRATEGY_SETTINGS_CHANGED", "strategy settings changed", metadata={"diff": diff}, strategy_id=strategy_id)
    if body.restart:
        await request.app.state.process_manager.restart()
    return {"strategy_id": strategy_id, "fields": _fields_for(strategy_id, request.app.state.store), "applies_on": "restart"}


@router.delete("/{strategy_id}/settings")
async def delete_strategy_settings(strategy_id: str, request: Request, _user: User):
    _fields_for(strategy_id, request.app.state.store)
    request.app.state.store.set_setting(f"strategy_overrides:{strategy_id}", {})
    return {"ok": True}


@router.post("/{strategy_id}/enable")
async def enable_strategy(strategy_id: str, request: Request, _user: User):
    if strategy_id != active_id():
        raise HTTPException(status_code=404, detail="strategy not found")
    control = dict(DEFAULT_CONTROL)
    control.update(request.app.state.store.get_setting("control", {}) or {})
    control["trading_enabled"] = True
    request.app.state.store.set_setting("control", control)
    request.app.state.store.insert_event(time.time(), "INFO", "TRADING_ENABLED", "strategy enabled")
    return control


@router.post("/{strategy_id}/disable")
async def disable_strategy(strategy_id: str, request: Request, _user: User):
    if strategy_id != active_id():
        raise HTTPException(status_code=404, detail="strategy not found")
    control = dict(DEFAULT_CONTROL)
    control.update(request.app.state.store.get_setting("control", {}) or {})
    control["trading_enabled"] = False
    request.app.state.store.set_setting("control", control)
    request.app.state.store.insert_event(time.time(), "WARNING", "TRADING_DISABLED", "strategy disabled")
    return control
