from __future__ import annotations

import asyncio
import json
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from sse_starlette.sse import EventSourceResponse
from starlette.middleware.base import BaseHTTPMiddleware

from dashboard.backend.auth import require_user
from dashboard.backend.exchange_client import ExchangeClient
from dashboard.backend.process_manager import ProcessManager
from dashboard.backend.routes import auth, bot, data, risk, strategies
from dashboard.backend.settings import settings
from dashboard.backend.state import compute_status
from dashboard.store import Store


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if (
            request.url.path.startswith("/api/")
            and request.method != "GET"
            and request.url.path != "/api/auth/login"
            and request.headers.get("X-Requested-With") != "dashboard"
        ):
            return JSONResponse({"detail": "CSRF header required"}, status_code=403)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response


async def _snapshot_loop(app):
    while True:
        try:
            current = compute_status(app.state.store, app.state.process_manager, app.state.exchange_client)
            app.state.latest_snapshot = {
                "status": current,
                "summary_light": summary_light_from_store(app.state.store, current),
                "positions": app.state.store.list_positions(),
            }
        except Exception as exc:
            logger.warning(f"dashboard snapshot failed: {exc}")
        await asyncio.sleep(2)


def summary_light_from_store(db, current):
    latest = db.latest_equity() or {}
    now = time.time()
    today_start = now - (now % 86400)
    trades = db.list_trades({}, limit=100000, offset=0)[0]
    return {
        "equity": latest.get("equity"),
        "unrealized": latest.get("unrealized_pnl"),
        "open_positions": len(db.list_positions()),
        "pnl_today": sum(float(row.get("pnl") or 0) for row in trades if float(row.get("closed_ts") or 0) >= today_start),
    }


@asynccontextmanager
async def lifespan(app):
    db_path = settings.dashboard_db_path
    app.state.store = Store(db_path)
    app.state.settings = settings
    app.state.exchange_client = ExchangeClient(
        app.state.store,
        settings.bot_config_path,
        Path(__file__).resolve().parents[2],
    )
    app.state.auth = __import__("dashboard.backend.auth", fromlist=["AuthManager"]).AuthManager(
        app.state.store, settings
    )
    app.state.process_manager = ProcessManager(
        app.state.store,
        settings,
        app.state.exchange_client,
        Path(__file__).resolve().parents[2],
    )
    app.state.wallet_cache = {"ts": 0.0, "data": None}
    app.state.latest_snapshot = None
    app.state.tasks = [
        asyncio.create_task(app.state.process_manager.run()),
        asyncio.create_task(_snapshot_loop(app)),
    ]
    yield
    for task in app.state.tasks:
        task.cancel()
    await asyncio.gather(*app.state.tasks, return_exceptions=True)


app = FastAPI(title="Trading Bot Dashboard", lifespan=lifespan)
app.add_middleware(CSRFMiddleware)


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    logger.error("dashboard request failed\n" + traceback.format_exc())
    return JSONResponse({"detail": "internal server error"}, status_code=500)


@app.exception_handler(HTTPException)
async def http_exception(request: Request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)


@app.get("/api/health")
async def health():
    return {"ok": True, "ts": time.time()}


@app.get("/api/stream")
async def stream(request: Request, _user=Depends(require_user)):
    async def generator():
        last_id = int(request.query_params.get("since_id", "0") or 0)
        last_heartbeat = time.monotonic()
        while True:
            if await request.is_disconnected():
                break
            snapshot = request.app.state.latest_snapshot
            if snapshot is not None:
                yield {"event": "snapshot", "data": json.dumps(snapshot, default=str)}
            events, _ = request.app.state.store.list_events({"since_id": last_id}, limit=100, offset=0)
            if events:
                events = list(reversed(events))
                last_id = max(int(row["id"]) for row in events)
                yield {"event": "events", "data": json.dumps(events, default=str)}
            if time.monotonic() - last_heartbeat >= 15:
                yield {"comment": "heartbeat"}
                last_heartbeat = time.monotonic()
            await asyncio.sleep(2)

    return EventSourceResponse(generator())


app.include_router(auth.router)
app.include_router(bot.router)
app.include_router(data.router)
app.include_router(risk.router)
app.include_router(strategies.router)

frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (frontend_dist / full_path).resolve()
        if full_path and candidate.is_file() and frontend_dist in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(frontend_dist / "index.html")

app.add_middleware(SecurityHeadersMiddleware)
