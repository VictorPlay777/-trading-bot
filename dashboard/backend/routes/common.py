from __future__ import annotations

import json
import asyncio
import inspect
import time
from typing import Annotated

from fastapi import Depends, Request

from dashboard.backend.auth import require_user
from dashboard.backend.state import compute_status


User = Annotated[str, Depends(require_user)]


def store(request: Request):
    return request.app.state.store


def exchange(request: Request):
    return request.app.state.exchange_client


async def exchange_call(request: Request, method, *args):
    result = await asyncio.to_thread(getattr(exchange(request), method), *args)
    if inspect.isawaitable(result):
        return await result
    return result


def manager(request: Request):
    return request.app.state.process_manager


def status(request: Request):
    return compute_status(request.app.state.store, request.app.state.process_manager, request.app.state.exchange_client)


def parse_json(value, default=None):
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def all_trades(db):
    return db.list_trades({}, limit=100000, offset=0)[0]


def filter_trades(rows, start=None, end=None):
    return [
        row for row in rows
        if (start is None or float(row.get("closed_ts") or row.get("opened_ts") or 0) >= start)
        and (end is None or float(row.get("closed_ts") or row.get("opened_ts") or 0) <= end)
    ]


def summary_light(request: Request):
    db = request.app.state.store
    current = status(request)
    equity = db.latest_equity() or {}
    positions = db.list_positions()
    trades = all_trades(db)
    now = time.time()
    today = time.gmtime(now)
    day_start = time.mktime((today.tm_year, today.tm_mon, today.tm_mday, 0, 0, 0, 0, 0, 0))
    return {
        "equity": equity.get("equity"),
        "unrealized": equity.get("unrealized_pnl"),
        "open_positions": len(positions),
        "pnl_today": sum(float(row.get("pnl") or 0) for row in trades if float(row.get("closed_ts") or 0) >= day_start),
        "status": current["state"],
    }
