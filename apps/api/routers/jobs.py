from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update

from agent.mcp_client import ToolUnavailable
from agent.nodes.scout import scout_search
from core.db import approvals, engine, jobs, row_dict, runs, saved_searches

from .. import dispatch
from ..auth.users import current_user
from ..schemas.models import JobCard, JobDetail, RunRef

router = APIRouter(prefix="/api", tags=["jobs"])


def _flags(summary: dict | None, data: dict) -> list[str]:
    return (summary or {}).get("flags", [])


@router.get("/jobs", response_model=list[JobCard])
def inbox(status: str | None = None, action: str | None = None, q: str | None = None, user: dict = Depends(current_user)):
    with engine().begin() as c:
        stmt = select(jobs).where(jobs.c.user_id == user["id"])
        if status:
            stmt = stmt.where(jobs.c.status == status)
        if action:
            stmt = stmt.where(jobs.c.action == action)
        rows = [row_dict(r) for r in c.execute(stmt)]
        pend = {r.job_id for r in c.execute(select(approvals.c.job_id).where(approvals.c.user_id == user["id"], approvals.c.status == "pending"))}
    out = []
    for r in rows:
        d = r["data"] or {}
        if q and q.lower() not in (d.get("title", "") + d.get("description", "")).lower():
            continue
        s = r.get("summary") or {}
        out.append(JobCard(job_id=r["job_id"], title=d.get("title", ""), category=d.get("category"), budget=d.get("budget"),
                           budget_type=d.get("budget_type"), status=r["status"], action=r.get("action"), fit=r.get("fit"),
                           risk=r.get("risk"), price=r.get("price"), connects=r.get("connects"), risk_flags=s.get("flags", []),
                           posted_at=d.get("posted_at"), has_approval=r["job_id"] in pend))
    order = {"awaiting_approval": 0, "analysing": 1, "queued": 2}
    return sorted(out, key=lambda j: (order.get(j.status, 3), -(j.fit or 0)))


@router.get("/jobs/{job_id}", response_model=JobDetail)
async def job_detail(job_id: str, user: dict = Depends(current_user)):
    with engine().begin() as c:
        row = c.execute(select(jobs).where(jobs.c.user_id == user["id"], jobs.c.job_id == job_id)).first()
        if not row:
            raise HTTPException(404, "job not found")
        r = row_dict(row)
        rr = [dict(x._mapping) for x in c.execute(select(runs).where(runs.c.user_id == user["id"], runs.c.job_id == job_id)
                                                  .order_by(runs.c.started_at.desc()).limit(10))]
        ap = c.execute(select(approvals.c.id).where(approvals.c.user_id == user["id"], approvals.c.job_id == job_id,
                                                    approvals.c.status == "pending")).first()
    v = {}
    if r.get("thread_id"):
        snap = await dispatch.RT.bid.aget_state({"configurable": {"thread_id": r["thread_id"]}})
        v = snap.values or {}
    return JobDetail(job=r["data"], status=r["status"], thread_id=r.get("thread_id"), spec=v.get("spec"), risk=v.get("risk"),
                     fit=v.get("fit"), decision=v.get("decision"), price=v.get("price"), draft=v.get("draft"),
                     verification=v.get("verification"), critiques=v.get("critiques", []), compliance=v.get("compliance"),
                     submission=v.get("submission"), node_log=v.get("node_log", []), runs=rr, approval_id=ap[0] if ap else None)


@router.post("/jobs/{job_id}/analyze", response_model=RunRef)
async def analyze(job_id: str, user: dict = Depends(current_user)):
    with engine().begin() as c:
        res = c.execute(update(jobs).where(jobs.c.user_id == user["id"], jobs.c.job_id == job_id,
                                           jobs.c.status.in_(["queued", "skipped", "watching", "waiting_marketplace"]),
                                           jobs.c.thread_id.is_(None)).values(status="queued"))
    await dispatch.enqueue("analyze_job", user_id=user["id"], job_id=job_id)
    return RunRef(status="queued" if res.rowcount else "already_analysed")


@router.post("/jobs/{job_id}/skip", response_model=RunRef)
def skip(job_id: str, user: dict = Depends(current_user)):
    with engine().begin() as c:
        c.execute(update(jobs).where(jobs.c.user_id == user["id"], jobs.c.job_id == job_id).values(status="skipped", action="skip"))
    return RunRef(status="skipped")


@router.post("/scout/run", response_model=RunRef)
async def scout_now(user: dict = Depends(current_user)):
    """Run the user's saved searches now (still through the Scout's MCP tools and the analysis queue)."""
    with engine().begin() as c:
        searches = [row_dict(r) for r in c.execute(select(saved_searches).where(saved_searches.c.user_id == user["id"]))]
    new = []
    try:
        for s in searches or [{"query": "", "category": None}]:
            new += (await scout_search(user["id"], s.get("query") or "", s.get("category"), 20))["new"]
    except ToolUnavailable as e:
        return RunRef(status="marketplace_unavailable", detail=str(e))
    for jid in new:
        await dispatch.enqueue("analyze_job", user_id=user["id"], job_id=jid)
    return RunRef(status="queued", detail=f"{len(new)} new job(s)")
