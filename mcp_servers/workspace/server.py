"""Workspace MCP server (A3): free calendar slots, tentative interview holds and email drafts.

Backed by a local mock calendar (working hours + existing busy events, stored per user in the app database).
The agent sees only these MCP tools; swapping in Google Calendar / Gmail means replacing `MockCalendar`.
Run: python -m mcp_servers.workspace.server --http --port 8003
"""

from __future__ import annotations

import argparse
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from sqlalchemy import select

from core import service_auth, tracing
from core.db import audit_log, engine, init_db, kv

mcp = FastMCP("gigbid-workspace", instructions="Calendar availability, tentative holds and email drafts for the freelancer.",
              stateless_http=True, json_response=True)


class Slot(BaseModel):
    start: str
    end: str


class Slots(BaseModel):
    slots: list[Slot]
    timezone: str


class Hold(BaseModel):
    id: str
    start: str
    end: str
    title: str
    status: str = "tentative"


class EmailDraft(BaseModel):
    id: str
    to: str
    subject: str
    body: str
    status: str = "draft"


def _uid(ctx: Context | None) -> str:
    req = None
    try:
        req = ctx.request_context.request if ctx else None
    except Exception:
        req = None
    if req is not None:
        uid = service_auth.verify(req.headers.get("authorization", "").removeprefix("Bearer ").strip())
        if not uid:
            raise PermissionError("unauthorized")
        if req.headers.get(tracing.TRACE_HEADER):
            tracing.trace_id_var.set(req.headers[tracing.TRACE_HEADER])
        return uid
    if service_auth.inprocess_user.get():
        return service_auth.inprocess_user.get()
    if os.environ.get("MARKETPLACE_ALLOW_ANON") == "1":
        return os.environ.get("MARKETPLACE_DEFAULT_USER", "test-user")
    raise PermissionError("authentication required")


class MockCalendar:
    """Working hours 09:00-17:00 Mon-Fri in the user's timezone offset; busy events + holds stored in kv."""

    def __init__(self, user_id: str):
        self.key = f"calendar:{user_id}"

    def _load(self) -> dict[str, Any]:
        with engine().begin() as c:
            row = c.execute(select(kv.c.value).where(kv.c.key == self.key)).first()
        return row[0] if row else {"tz_offset_h": 5, "busy": [], "holds": [], "drafts": []}

    def _save(self, data: dict[str, Any]) -> None:
        with engine().begin() as c:
            c.execute(kv.delete().where(kv.c.key == self.key))
            c.execute(kv.insert().values(key=self.key, value=data))

    def free_slots(self, days: int, duration_min: int, now: datetime | None = None) -> tuple[list[Slot], str]:
        data = self._load()
        tz = timezone(timedelta(hours=data.get("tz_offset_h", 5)))
        now = (now or datetime.now(tz)).astimezone(tz)
        busy = [(datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"])) for b in data["busy"] + data["holds"]]
        out: list[Slot] = []
        day = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        while len(out) < 6 and day < now + timedelta(days=days + 1):
            if day.weekday() < 5:
                for hour in (10, 12, 15):
                    s = day.replace(hour=hour)
                    e = s + timedelta(minutes=duration_min)
                    if all(e <= bs or s >= be for bs, be in busy):
                        out.append(Slot(start=s.isoformat(), end=e.isoformat()))
            day += timedelta(days=1)
        return out, f"UTC{data.get('tz_offset_h', 5):+d}"

    def hold(self, start: str, end: str, title: str) -> Hold:
        data = self._load()
        for h in data["holds"]:
            if h["start"] == start and h["title"] == title:
                return Hold(**h)
        h = Hold(id="h-" + uuid.uuid4().hex[:8], start=start, end=end, title=title)
        data["holds"].append(h.model_dump())
        self._save(data)
        return h

    def draft(self, to: str, subject: str, body: str) -> EmailDraft:
        data = self._load()
        d = EmailDraft(id="e-" + uuid.uuid4().hex[:8], to=to, subject=subject, body=body)
        data["drafts"].append(d.model_dump())
        self._save(data)
        return d


def _audit(uid: str, tool: str, args: dict, result: Any) -> None:
    from core.pii import mask

    with engine().begin() as c:
        c.execute(audit_log.insert().values(user_id=uid, tool=f"workspace.{tool}", args=mask(args), result=mask(result),
                                            trace_id=tracing.current_trace_id()))


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False),
          description="Free interview slots in the freelancer's calendar over the next N days.")
async def free_slots(days: Annotated[int, Field(ge=1, le=14)] = 5, duration_min: Annotated[int, Field(ge=15, le=120)] = 30,
                     ctx: Context | None = None) -> Slots:
    uid = _uid(ctx)
    slots, tz = MockCalendar(uid).free_slots(days, duration_min)
    return Slots(slots=slots, timezone=tz)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True, destructiveHint=False, openWorldHint=False),
          description="Create a TENTATIVE calendar hold for a proposed interview slot (idempotent on start+title).")
async def create_interview_hold(start: Annotated[str, Field(min_length=10, max_length=40)],
                                end: Annotated[str, Field(min_length=10, max_length=40)],
                                title: Annotated[str, Field(min_length=1, max_length=120)], ctx: Context | None = None) -> Hold:
    uid = _uid(ctx)
    h = MockCalendar(uid).hold(start, end, title)
    _audit(uid, "create_interview_hold", {"start": start, "title": title}, h.model_dump())
    return h


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False),
          description="Create an email DRAFT (never sent automatically).")
async def create_email_draft(to: Annotated[str, Field(min_length=3, max_length=200)],
                             subject: Annotated[str, Field(min_length=1, max_length=200)],
                             body: Annotated[str, Field(min_length=1, max_length=5000)], ctx: Context | None = None) -> EmailDraft:
    uid = _uid(ctx)
    d = MockCalendar(uid).draft(to, subject, body)
    _audit(uid, "create_email_draft", {"to": to, "subject": subject}, {"id": d.id})
    return d


def http_app():
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    app = mcp.streamable_http_app()

    class Bearer(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.url.path == "/health":
                return JSONResponse({"ok": True})
            if not service_auth.verify(request.headers.get("authorization", "").removeprefix("Bearer ").strip()):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    app.add_middleware(Bearer)
    return app


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", action="store_true")
    ap.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("WORKSPACE_MCP_PORT", "8003")))
    a = ap.parse_args()
    init_db()
    if a.http:
        import uvicorn

        uvicorn.run(http_app(), host=a.host, port=a.port, log_level="warning")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
