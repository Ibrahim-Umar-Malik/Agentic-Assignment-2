"""Scout: run saved searches (Marketplace read), de-duplicate by fingerprint, queue new jobs (idempotently)."""

from __future__ import annotations

import hashlib
import re
import time

from sqlalchemy import select

from core.db import engine, jobs

from ..mcp_client import ToolGateway
from .common import node


def fingerprint(job: dict) -> str:
    title = re.sub(r"(?i)\(reposted\)|- urgent|[^a-z0-9 ]", "", job.get("title", "").lower()).strip()
    desc = re.sub(r"\s+", " ", job.get("description", "").lower())[:200]
    return hashlib.sha256(f"{job.get('client_id')}|{title}|{desc}".encode()).hexdigest()[:20]


def find_duplicate(user_id: str, job: dict) -> str | None:
    fp = fingerprint(job)
    with engine().begin() as c:
        row = c.execute(select(jobs.c.job_id).where(jobs.c.user_id == user_id, jobs.c.dedup_key == fp,
                                                    jobs.c.job_id != job["id"])).first()
    return row[0] if row else None


async def scout_search(user_id: str, query: str, category: str | None, limit: int) -> dict:
    """Called by the worker on each saved search's schedule. Inserting with the (user, job) primary key makes
    queueing idempotent: a worker restart never queues (or analyses) the same job twice."""
    res = await ToolGateway(user_id).call("scout", "marketplace", "search_jobs", {"query": query, "category": category, "limit": limit})
    new = []
    with engine().begin() as c:
        for j in res.get("jobs", []):
            exists = c.execute(select(jobs.c.job_id).where(jobs.c.user_id == user_id, jobs.c.job_id == j["id"])).first()
            if exists:
                continue
            c.execute(jobs.insert().values(user_id=user_id, job_id=j["id"], data=j, status="queued", dedup_key=fingerprint(j),
                                           connects=j.get("connects_cost"), created_at=time.time(), updated_at=time.time()))
            new.append(j["id"])
    return {"new": new, "seen": len(res.get("jobs", []))}


@node("scout")
async def intake(state: dict) -> dict:
    job = state["job"]
    dup = find_duplicate(state["user_id"], job)
    return {"meta": {"duplicate_of": dup} if dup else {}, "status": "analysing",
            "_summary": f"duplicate of {dup}" if dup else "new job queued for analysis"}
