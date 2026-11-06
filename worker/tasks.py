"""Background work: scheduled scouting, analysis, resumes and pipeline sync. Executed by the Arq worker
(worker/main.py) when REDIS_URL is set, or by an in-process loop in the API for single-container deployments.
Every task is idempotent (see agent/runner.py and agent/nodes/scout.py)."""

from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy import select, update

from agent import runner
from agent.mcp_client import ToolGateway, ToolUnavailable
from agent.memory.promotion_rules import record_outcome
from agent.nodes.scout import scout_search
from core import config
from core.db import conversations, engine, jobs, kv, pipeline, row_dict, saved_searches, users

log = logging.getLogger("gigbid.worker")
STAGE = {"viewed": "viewed", "replied": "replied", "interview": "interview", "hired": "hired", "lost": "lost", "submitted": "submitted"}


def min_interval(user: dict, search: dict) -> int:
    live = (user.get("settings") or {}).get("marketplace") == "upwork_live"
    floor = config.get("scheduling.live_scout_interval_min" if live else "scheduling.gigsim_scout_interval_min", 30)
    return max(int(search.get("interval_min") or floor), floor)  # live mode never polls faster than the justified floor


async def scheduler_tick(rt, enqueue) -> dict:
    now = time.time()
    with engine().begin() as c:
        searches = [row_dict(r) for r in c.execute(select(saved_searches))]
        all_users = {r.id: row_dict(r) for r in c.execute(select(users))}
    started = 0
    for s in searches:
        user = all_users.get(s["user_id"])
        if not user or now - (s.get("last_run") or 0) < min_interval(user, s) * 60:
            continue
        with engine().begin() as c:
            c.execute(update(saved_searches).where(saved_searches.c.id == s["id"]).values(last_run=now))
        try:
            res = await scout_search(s["user_id"], s["query"] or "", s.get("category"), config.get("scheduling.max_jobs_per_scout", 20))
        except ToolUnavailable as e:
            log.warning("scout skipped, marketplace unavailable: %s", e)
            continue
        for jid in res["new"]:
            await enqueue("analyze_job", user_id=s["user_id"], job_id=jid)
            started += 1
    # retry jobs parked while the marketplace was down
    with engine().begin() as c:
        parked = [(r.user_id, r.job_id) for r in c.execute(select(jobs.c.user_id, jobs.c.job_id).where(jobs.c.status == "waiting_marketplace"))]
    for uid, jid in parked[:20]:
        await enqueue("analyze_job", user_id=uid, job_id=jid)
    for uid in all_users:
        await enqueue("sync_pipeline", user_id=uid)
    return {"analyses_queued": started, "retried": len(parked)}


async def sync_pipeline(rt, enqueue, user_id: str) -> dict:
    """Marketplace events -> pipeline board; outcomes -> outcome memory (via promotion rule); new client
    messages -> conversation graph drafts awaiting approval."""
    gw = ToolGateway(user_id)
    key = f"events_cursor:{user_id}"
    with engine().begin() as c:
        row = c.execute(select(kv.c.value).where(kv.c.key == key)).first()
    cursor = (row[0] or {}).get("since", 0) if row else 0
    try:
        evs = (await gw.call("sync", "marketplace", "list_events", {"since": cursor}))["events"]
    except ToolUnavailable:
        return {"status": "marketplace_unavailable"}
    changed = 0
    for e in evs:
        cursor = max(cursor, e["id"])
        stage = STAGE.get(e["kind"])
        if not stage or not e.get("job_id"):
            continue
        with engine().begin() as c:
            c.execute(update(pipeline).where(pipeline.c.user_id == user_id, pipeline.c.job_id == e["job_id"])
                      .values(stage=stage, thread_id=e.get("thread_id"), updated_at=time.time()))
            p = c.execute(select(pipeline).where(pipeline.c.user_id == user_id, pipeline.c.job_id == e["job_id"])).first()
        changed += 1
        if stage in ("replied", "lost", "hired") and p is not None:
            snap = await rt.bid.aget_state({"configurable": {"thread_id": f"{user_id}:{e['job_id']}"}})
            letter = ((snap.values or {}).get("draft") or {}).get("cover_letter", "")
            if letter:
                await record_outcome(rt.store, user_id, p.category, letter, stage)
    with engine().begin() as c:
        c.execute(kv.delete().where(kv.c.key == key))
        c.execute(kv.insert().values(key=key, value={"since": cursor}))
    started = await check_messages(rt, user_id)
    return {"events": len(evs), "changed": changed, "conversations_started": started}


async def check_messages(rt, user_id: str) -> int:
    gw = ToolGateway(user_id)
    threads = (await gw.call("sync", "marketplace", "list_messages", {}))["threads"]
    started = 0
    for t in threads:
        msgs = t.get("messages") or []
        if not msgs or msgs[-1].get("sender", msgs[-1].get("from")) != "client":
            continue
        last = msgs[-1]
        with engine().begin() as c:
            conv = c.execute(select(conversations).where(conversations.c.user_id == user_id, conversations.c.thread_id == t["id"])).first()
        if conv and conv.last_seen_msg == last["id"]:
            continue
        job = None
        if t.get("job_id"):
            with engine().begin() as c:
                jr = c.execute(select(jobs).where(jobs.c.user_id == user_id, jobs.c.job_id == t["job_id"])).first()
            job = row_dict(jr)["data"] if jr else {"id": t["job_id"]}
        with engine().begin() as c:
            pr = c.execute(select(pipeline).where(pipeline.c.user_id == user_id, pipeline.c.job_id == t.get("job_id"))).first()
        proposal = {"bid_amount": pr.bid, "id": pr.proposal_id} if pr else {}
        await runner.start_conversation(rt, user_id, t, {"id": last["id"], "body": last["body"]}, job, proposal)
        started += 1
    return started


def new_id() -> str:
    return uuid.uuid4().hex[:12]
