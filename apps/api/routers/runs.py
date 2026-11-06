from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from core.db import engine, runs, trace_spans

from .. import dispatch
from ..auth.users import current_user
from ..schemas.models import RunOut, TraceOut

router = APIRouter(prefix="/api", tags=["runs"])


@router.get("/runs", response_model=list[RunOut])
def list_runs(limit: int = 50, user: dict = Depends(current_user)):
    with engine().begin() as c:
        return [RunOut(**dict(r._mapping)) for r in c.execute(select(runs).where(runs.c.user_id == user["id"])
                                                              .order_by(runs.c.started_at.desc()).limit(min(limit, 200)))]


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, user: dict = Depends(current_user)):
    with engine().begin() as c:
        r = c.execute(select(runs).where(runs.c.id == run_id, runs.c.user_id == user["id"])).first()
    if not r:
        raise HTTPException(404, "run not found")
    return RunOut(**dict(r._mapping))


def _trace(trace_id: str, user_id: str | None) -> TraceOut:
    with engine().begin() as c:
        stmt = select(trace_spans).where(trace_spans.c.trace_id == trace_id).order_by(trace_spans.c.start)
        rows = [dict(r._mapping) for r in c.execute(stmt)]
    if user_id is not None:
        rows = [r for r in rows if r["user_id"] in (user_id, None)]
    if not rows:
        raise HTTPException(404, "trace not found")
    llm_rows = [r for r in rows if r["kind"] == "llm"]
    totals = {"spans": len(rows), "duration_s": round(max(r["end"] for r in rows) - min(r["start"] for r in rows), 3),
              "tokens": sum((r["attrs"] or {}).get("tokens_in", 0) + (r["attrs"] or {}).get("tokens_out", 0) for r in llm_rows),
              "cost_usd": round(sum((r["attrs"] or {}).get("cost_usd", 0) for r in llm_rows), 6),
              "tool_calls": sum(1 for r in rows if r["kind"] == "tool")}
    return TraceOut(trace_id=trace_id, spans=rows, totals=totals)


@router.get("/traces/{trace_id}", response_model=TraceOut)
def trace(trace_id: str, user: dict = Depends(current_user)):
    return _trace(trace_id, user["id"])


@router.get("/share/trace/{trace_id}", response_model=TraceOut)
def shared_trace(trace_id: str):
    """Public, read-only trace (spans are PII-masked at write time) for README / report links."""
    return _trace(trace_id, None)


@router.get("/threads/{thread_id}/history")
async def history(thread_id: str, user: dict = Depends(current_user)) -> list[dict]:
    """Checkpoint history of a job thread: replay any job from any node (C6)."""
    if not thread_id.startswith(user["id"] + ":"):
        raise HTTPException(404, "thread not found")
    out = []
    async for s in dispatch.RT.bid.aget_state_history({"configurable": {"thread_id": thread_id}}):
        out.append({"checkpoint_id": s.config["configurable"].get("checkpoint_id"), "next": list(s.next),
                    "step": (s.metadata or {}).get("step"), "status": (s.values or {}).get("status")})
    return out


@router.post("/threads/{thread_id}/replay/{checkpoint_id}")
async def replay(thread_id: str, checkpoint_id: str, user: dict = Depends(current_user)) -> dict:
    """Re-run a job thread from a chosen checkpoint (time travel). Writes are still protected by idempotency."""
    if not thread_id.startswith(user["id"] + ":"):
        raise HTTPException(404, "thread not found")
    cfg = {"configurable": {"thread_id": thread_id, "checkpoint_id": checkpoint_id}}
    out = await dispatch.RT.bid.ainvoke(None, cfg)
    return {"status": out.get("status"), "decision": out.get("decision")}
