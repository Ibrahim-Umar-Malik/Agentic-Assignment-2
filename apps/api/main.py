"""GigBid API (FastAPI). Run: uvicorn apps.api.main:app --port 8080"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from agent import runner
from agent.runtime import Runtime
from core import tracing
from core.db import init_db
from core.pii import install_logging

from . import dispatch, streaming
from .routers import analytics, approvals, auth, jobs, messages, runs, settings

ROOT = Path(__file__).resolve().parents[2]
WEB_DIST = Path(os.environ.get("WEB_DIST", ROOT / "apps" / "web" / "dist"))


def seed_reviewer() -> None:
    """Reviewer login preloaded with a persona. Credentials come only from the environment."""
    from .auth.users import create_user, find_user
    from .routers.settings import seed_searches

    email, pw = os.environ.get("REVIEWER_EMAIL"), os.environ.get("REVIEWER_PASSWORD")
    if not email or not pw:
        return
    u = find_user(email) or create_user(email, pw, "Reviewer", os.environ.get("REVIEWER_PERSONA", "ai_ml"),
                                        {"onboarded": True})
    seed_searches(u)


@asynccontextmanager
async def lifespan(app: FastAPI):
    install_logging()
    init_db()
    seed_reviewer()
    rt = await Runtime().__aenter__()
    dispatch.RT = rt
    stop = asyncio.Event()
    bg = []
    if not dispatch.use_worker():
        bg.append(asyncio.create_task(runner.recover_decided(rt)))
        if os.environ.get("GIGBID_SCHEDULER", "1") == "1":
            bg.append(asyncio.create_task(dispatch.inline_scheduler(stop, int(os.environ.get("GIGBID_SCHEDULER_EVERY_S", "60")))))
    yield
    stop.set()
    for t in bg:
        t.cancel()
    await rt.__aexit__(None, None, None)


app = FastAPI(title="GigBid API", version="1.0.0", lifespan=lifespan,
              description="Multi-agent freelancer copilot. Every outbound proposal and message requires human approval.")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def trace_ids(request: Request, call_next):
    """One trace id from the UI request onward: taken from the client header or minted here."""
    tid = request.headers.get(tracing.TRACE_HEADER) or tracing.new_trace_id()
    tracing.trace_id_var.set(tid)
    resp = await call_next(request)
    resp.headers[tracing.TRACE_HEADER] = tid
    return resp


for r in (auth.router, jobs.router, approvals.router, messages.router, runs.router, analytics.router, settings.router, streaming.router):
    app.include_router(r)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    from agent.mcp_client import ToolUnavailable

    if isinstance(exc, ToolUnavailable):
        return JSONResponse({"detail": "marketplace unavailable", "server": exc.server}, status_code=503)
    return JSONResponse({"detail": f"internal error: {type(exc).__name__}"}, status_code=500)


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True}


# Single-page app: serve the built React app for every non-API path (one public URL for UI + API).
@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    f = WEB_DIST / path
    if path and f.is_file() and WEB_DIST in f.resolve().parents:
        return FileResponse(f)
    index = WEB_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"detail": "web app not built; run `make web`"}, status_code=404)
