"""SSE bridge to LangGraph streams: the runner publishes each node update (stream_mode="updates") to the event
bus; this endpoint relays them so the user never stares at a spinner. History is replayed on (re)connect."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from core import events
from core.db import engine, runs

from .auth.users import current_user

router = APIRouter(tags=["runs"])


@router.get("/api/runs/{run_id}/stream")
async def stream_run(run_id: str, user: dict = Depends(current_user)):
    with engine().begin() as c:
        row = c.execute(select(runs.c.user_id).where(runs.c.id == run_id)).first()
    if not row or row.user_id != user["id"]:
        raise HTTPException(404, "run not found")

    async def gen():
        async for ev in events.subscribe(f"run:{run_id}"):
            yield {"event": ev.get("type", "message"), "data": json.dumps(ev)}
            if ev.get("type") == "end":
                break

    return EventSourceResponse(gen())


@router.get("/api/events")
async def user_events(user: dict = Depends(current_user)):
    """Per-user feed (run started/finished) so the inbox and pipeline update live."""

    async def gen():
        async for ev in events.subscribe(f"user:{user['id']}"):
            yield {"event": ev.get("type", "message"), "data": json.dumps(ev)}

    return EventSourceResponse(gen())
