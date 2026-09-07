from __future__ import annotations

import time
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from dashboard.backend.routes.common import User, all_trades, exchange_call, filter_trades, status
from dashboard.backend.stats import (
    by_strategy,
    compute_metrics,
    cumulative_pnl,
    daily_pnl,
    drawdown_series,
    period_bounds,
)


router = APIRouter(prefix="/api", tags=["data"])


class ConfirmBody(BaseModel):
    confirm: bool


class SLTPBody(BaseModel):
    stop_loss: float | None = Field(default=None)
    tp1: float | None = Field(default=None)
    tp2: float | None = Field(default=None)
    tp3: float | None = Field(default=None)


def _position_from_exchange(row):
    side = row.get("side")
    return {
        "symbol": row.get("symbol"),
        "side": "long" if side == "Buy" else "short" if side == "Sell" else side,
        "qty": float(row.get("size", 0) or 0),
        "entry_price": float(row.get("avgPrice", 0) or 0),
        "mark_price": float(row.get("markPrice", 0) or 0),
        "unrealized_pnl": float(row.get("unrealisedPnl", row.get("unrealizedPnl", 0)) or 0),
        "leverage": row.get("leverage"),
        "source": "exchange",
        "raw": row,
    }


def _event_rows(rows):
    import json
    for row in rows:
        value = row.pop("metadata_json", None)
        if value:
            try:
                row["metadata"] = json.loads(value)
            except json.JSONDecodeError:
                row["metadata"] = value
    return rows


@router.get("/status")
async def get_status(request: Request, _user: User):
    return status(request)


@router.get("/summary")
async def summary(request: Request, _user: User):
    db = request.app.state.store
    current = status(request)
    now = time.time()
    latest = db.latest_equity() or {}
    wallet = latest if current["process_running"] and latest.get("ts") and now - latest["ts"] < 120 else None
    if wallet is None:
        cache = request.app.state.wallet_cache
        if now - cache["ts"] >= 30:
            cache["data"] = await exchange_call(request, "wallet")
            cache["ts"] = now
        response = cache["data"] or {}
        values = ((response.get("result") or {}).get("list") or [{}])[0]
        wallet = {
            "equity": float(values.get("totalEquity", 0) or 0),
            "wallet_balance": float(values.get("totalWalletBalance", 0) or 0),
            "available_balance": float(values.get("totalAvailableBalance", 0) or 0),
            "unrealized_pnl": float(values.get("totalPerpUPL", 0) or 0),
        }
    trades = all_trades(db)
    bounds = {period: period_bounds(period) for period in ("today", "7d", "30d")}
    pnl = {
        period: sum(
            float(row.get("pnl") or 0)
            for row in trades
            if (bounds[period][0] is None or float(row.get("closed_ts") or 0) >= bounds[period][0])
            and (bounds[period][1] is None or float(row.get("closed_ts") or 0) <= bounds[period][1])
        )
        for period in bounds
    }
    snapshots = db.list_equity(now - 90 * 86400, now, limit=5000)
    peak = max((float(row.get("equity") or 0) for row in snapshots), default=0)
    current_equity = float(wallet.get("equity") or 0)
    drawdown = {
        "usd": max(0.0, peak - current_equity),
        "pct": (max(0.0, peak - current_equity) / peak * 100) if peak > 0 else None,
    }
    positions = db.list_positions()
    return {
        "status": current,
        "wallet": {key: wallet.get(key) for key in ("equity", "wallet_balance", "available_balance", "unrealized_pnl")},
        "pnl_today": pnl["today"],
        "pnl_7d": pnl["7d"],
        "pnl_30d": pnl["30d"],
        "realized_pnl_all": sum(float(row.get("pnl") or 0) for row in trades),
        "drawdown": drawdown,
        "drawdown_source": "equity_snapshots" if snapshots else ("trades" if trades else None),
        "open_positions": len(positions),
        "trades_today": sum(1 for row in trades if float(row.get("closed_ts") or 0) >= bounds["today"][0]),
        "kill_switch": db.get_setting("kill_switch_state", {}) or {},
        "risk": current["risk"],
        "control": current["control"],
    }


@router.get("/positions")
async def positions(request: Request, _user: User):
    db = request.app.state.store
    current = status(request)
    rows = db.list_positions()
    if current["substatus"] == "heartbeat_stale":
        response = await exchange_call(request, "positions")
        exchange_rows = ((response or {}).get("result") or {}).get("list") or []
        if exchange_rows:
            return [_position_from_exchange(row) for row in exchange_rows if float(row.get("size", 0) or 0) > 0]
    return [{**row, "source": "bot"} for row in rows]


@router.get("/positions/{symbol}")
async def position_detail(symbol: str, request: Request, _user: User):
    rows = await positions(request, _user)
    item = next((row for row in rows if row.get("symbol") == symbol), None)
    if item is None:
        raise HTTPException(status_code=404, detail="position not found")
    orders = await exchange_call(request, "open_orders", symbol)
    order_rows = ((orders or {}).get("result") or {}).get("list") or []
    fills = request.app.state.store.list_fills(symbol, int((time.time() - 86400) * 1000), int(time.time() * 1000))
    events, _ = request.app.state.store.list_events({"symbol": symbol}, limit=50, offset=0)
    return {**item, "open_orders": order_rows, "fills": fills, "events": _event_rows(events)}


@router.post("/positions/{symbol}/close")
async def close_position(symbol: str, body: ConfirmBody, request: Request, _user: User):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirmation required")
    response = await exchange_call(request, "positions")
    rows = ((response or {}).get("result") or {}).get("list") or []
    row = next((item for item in rows if item.get("symbol") == symbol and float(item.get("size", 0) or 0) > 0), None)
    if row is None:
        raise HTTPException(status_code=400, detail="no live position")
    side = "long" if row.get("side") == "Buy" else "short"
    result = await exchange_call(request, "close_position", symbol, side, float(row["size"]))
    request.app.state.store.insert_event(
        time.time(), "WARNING", "POSITION_MANUAL_CLOSE", "manual position close requested",
        symbol=symbol, metadata={"result": result},
    )
    return {"ok": result is not None, "result": result}


@router.post("/positions/{symbol}/cancel-orders")
async def cancel_orders(symbol: str, body: ConfirmBody, request: Request, _user: User):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirmation required")
    response = await exchange_call(request, "open_orders", symbol)
    rows = ((response or {}).get("result") or {}).get("list") or []
    results = [await exchange_call(request, "cancel_order", symbol, row.get("orderId")) for row in rows if row.get("orderId")]
    return {"ok": True, "results": results}


@router.post("/positions/{symbol}/sltp")
async def sltp(symbol: str, body: SLTPBody, request: Request, _user: User):
    current = status(request)
    if current["state"] not in {"RUNNING", "PAUSED"}:
        raise HTTPException(status_code=409, detail="bot must be running or paused")
    rows = await positions(request, _user)
    position = next((row for row in rows if row.get("symbol") == symbol), None)
    if position is None:
        raise HTTPException(status_code=400, detail="position not found")
    mark = float(position.get("mark_price") or 0)
    if mark <= 0:
        raise HTTPException(status_code=400, detail="mark price unavailable")
    side = position.get("side")
    prices = [value for value in (body.stop_loss, body.tp1, body.tp2, body.tp3) if value is not None]
    if any(value <= 0 for value in prices):
        raise HTTPException(status_code=400, detail="prices must be positive")
    if side == "long":
        if body.stop_loss is not None and body.stop_loss >= mark:
            raise HTTPException(status_code=400, detail="long stop loss must be below mark")
        if any(value <= mark for value in (body.tp1, body.tp2, body.tp3) if value is not None):
            raise HTTPException(status_code=400, detail="long take profit must be above mark")
    elif side == "short":
        if body.stop_loss is not None and body.stop_loss <= mark:
            raise HTTPException(status_code=400, detail="short stop loss must be above mark")
        if any(value >= mark for value in (body.tp1, body.tp2, body.tp3) if value is not None):
            raise HTTPException(status_code=400, detail="short take profit must be below mark")
    override = body.model_dump()
    override["ts"] = time.time()
    overrides = request.app.state.store.get_setting("position_overrides", {}) or {}
    overrides[symbol] = override
    request.app.state.store.set_setting("position_overrides", overrides)
    request.app.state.store.insert_event(
        time.time(), "INFO", "SLTP_UPDATE_REQUESTED", "position SL/TP update requested",
        symbol=symbol, metadata=override,
    )
    interval = getattr(__import__("selective_config", fromlist=["ProductionConfig"]).ProductionConfig(), "position_loop_interval_sec", 2.0)
    return {"ok": True, "applied_by_bot_within_sec": interval}


@router.get("/trades")
async def trades(
    request: Request,
    _user: User,
    period: str = "all",
    start: float | None = None,
    end: float | None = None,
    symbol: str | None = None,
    strategy: str | None = None,
    side: str | None = None,
    result: str | None = None,
    exit_reason: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    sort: str = "closed_ts",
    order: str = "desc",
):
    start_ts, end_ts = period_bounds(period, start, end)
    rows = filter_trades(all_trades(request.app.state.store), start_ts, end_ts)
    if symbol:
        rows = [row for row in rows if row.get("symbol") == symbol]
    if strategy:
        rows = [row for row in rows if row.get("strategy_id") == strategy]
    if side:
        rows = [row for row in rows if row.get("side") == side]
    if exit_reason:
        rows = [row for row in rows if row.get("exit_reason") == exit_reason]
    if result == "win":
        rows = [row for row in rows if float(row.get("pnl") or 0) > 0]
    elif result == "loss":
        rows = [row for row in rows if float(row.get("pnl") or 0) <= 0]
    rows.sort(key=lambda row: row.get(sort) or 0, reverse=order.lower() != "asc")
    total = len(rows)
    return {"items": rows[offset:offset + limit], "total": total, "filters": request.app.state.store.trade_filter_options()}


@router.get("/trades/{trade_id}")
async def trade_detail(trade_id: str, request: Request, _user: User):
    import json
    row = request.app.state.store.get_trade(trade_id)
    if row is None:
        raise HTTPException(status_code=404, detail="trade not found")
    raw = row.get("raw_json")
    parsed_raw = json.loads(raw) if raw else None
    row["raw_json"] = parsed_raw
    row["raw"] = parsed_raw
    opened = float(row.get("opened_ts") or 0)
    closed = float(row.get("closed_ts") or time.time())
    row["fills"] = request.app.state.store.list_fills(row.get("symbol"), int((opened - 60) * 1000), int((closed + 60) * 1000))
    events, _ = request.app.state.store.list_events({
        "symbol": row.get("symbol"), "start_ts": opened - 60, "end_ts": closed + 60,
    }, limit=1000, offset=0)
    row["events"] = _event_rows(events)
    return row


@router.get("/stats")
async def stats(request: Request, _user: User, period: str = "all", start: float | None = None, end: float | None = None):
    start_ts, end_ts = period_bounds(period, start, end)
    rows = filter_trades(all_trades(request.app.state.store), start_ts, end_ts)
    cumulative = cumulative_pnl(rows)
    now = time.time()
    equity = request.app.state.store.list_equity(start_ts or 0, end_ts or now, limit=1000)
    notes = []
    if equity:
        notes.append(f"equity history starts at {equity[0]['ts']}")
    metrics = compute_metrics(rows)
    if metrics.get("sharpe_note"):
        notes.append(metrics["sharpe_note"])
    return {
        "metrics": metrics,
        "daily_pnl": daily_pnl(rows),
        "cumulative_pnl": cumulative,
        "drawdown": drawdown_series(cumulative),
        "trades_per_day": daily_pnl(rows),
        "equity_curve": equity,
        "by_strategy": by_strategy(rows),
        "notes": notes,
    }


@router.get("/events")
async def events(
    request: Request,
    _user: User,
    level: str | None = None,
    event_type: str | None = None,
    symbol: str | None = None,
    start: float | None = None,
    end: float | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    since_id: int | None = None,
):
    rows, total = request.app.state.store.list_events(
        {"level": level, "event_type": event_type, "symbol": symbol, "start_ts": start, "end_ts": end, "since_id": since_id},
        limit, offset,
    )
    return {"items": _event_rows(rows), "total": total, "event_types": request.app.state.store.distinct_event_types()}


@router.get("/signals")
async def signals(
    request: Request,
    _user: User,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    allowed: bool | None = None,
):
    filters = {}
    rows = request.app.state.store.list_signals(limit, offset, filters)
    if allowed is not None:
        rows = [row for row in rows if bool(row.get("allowed")) == allowed]
    return {"items": rows}
