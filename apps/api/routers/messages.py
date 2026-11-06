from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from agent.mcp_client import ToolGateway, ToolUnavailable
from core.db import approvals, conversations, engine, row_dict

from .. import dispatch
from ..auth.users import current_user
from ..schemas.models import RunRef

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.get("")
async def threads(user: dict = Depends(current_user)) -> dict:
    """Client threads (from the marketplace, through MCP) with GigBid's suggested reply awaiting approval."""
    try:
        live = (await ToolGateway(user["id"]).call("sync", "marketplace", "list_messages", {}))["threads"]
        available = True
    except ToolUnavailable:
        live, available = [], False
    with engine().begin() as c:
        convs = {r.thread_id: row_dict(r) for r in c.execute(select(conversations).where(conversations.c.user_id == user["id"]))}
        pend = {row_dict(r)["payload"].get("thread_id"): row_dict(r) for r in c.execute(
            select(approvals).where(approvals.c.user_id == user["id"], approvals.c.kind == "message", approvals.c.status == "pending"))}
    out = []
    for t in live:
        a = pend.get(t["id"])
        out.append({"thread": t, "conversation": convs.get(t["id"]), "approval": {"id": a["id"], "payload": a["payload"]} if a else None})
    return {"threads": out, "marketplace_available": available}


@router.post("/sync", response_model=RunRef)
async def sync(user: dict = Depends(current_user)):
    await dispatch.enqueue("sync_pipeline", user_id=user["id"])
    return RunRef(status="queued")
