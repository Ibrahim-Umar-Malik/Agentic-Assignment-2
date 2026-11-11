"""Runs graphs for the API and the worker: streams node progress to the event bus, records runs, approvals,
inbox state, dead letters and the degraded mode. Shared so a crash in either process resumes the same way."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from langgraph.types import Command
from sqlalchemy import select, update

from core import events, tracing
from core.db import approvals, conversations, dead_letter, engine, jobs, row_dict, runs, users
from core.personas import persona_floor

from .mcp_client import ToolUnavailable
from .runtime import Runtime

log = logging.getLogger("gigbid.runner")


def user_meta(user: dict) -> dict:
    s = user.get("settings") or {}
    return {"hourly_floor": s.get("hourly_floor", persona_floor(user.get("persona"))), "hours_per_week": s.get("hours_per_week", 20),
            "portfolio_id": f"{user.get('persona') or 'ai_ml'}:{user['id']}" if s.get("own_portfolio") else (user.get("persona") or "ai_ml"),
            "deleted_items": s.get("deleted_items", []), "autonomy": s.get("autonomy", "suggest")}


def get_user(user_id: str) -> dict:
    with engine().begin() as c:
        row = c.execute(select(users).where(users.c.id == user_id)).first()
    return row_dict(row) if row else {"id": user_id, "persona": "ai_ml", "settings": {}}


def _summary_from_state(v: dict) -> dict:
    return {"fit": (v.get("fit") or {}).get("fit_score"), "risk": (v.get("risk") or {}).get("risk_score"),
            "action": (v.get("decision") or {}).get("action"), "price": (v.get("price") or {}).get("amount"),
            "status": v.get("status"), "flags": sorted({f["kind"] for f in (v.get("risk") or {}).get("flags", []) if f.get("severity", 0) >= 0.3}),
            "reason": v.get("status_reason"), "experiment_arm": (v.get("meta") or {}).get("experiment_arm")}


async def _stream(rt: Runtime, graph: Any, graph_name: str, user_id: str, thread_id: str, job_id: str | None, inp: Any,
                  trace_id: str) -> dict:
    run_id = uuid.uuid4().hex[:16]
    tracing.trace_id_var.set(trace_id)
    tracing.user_id_var.set(user_id)
    with engine().begin() as c:
        c.execute(runs.insert().values(id=run_id, user_id=user_id, job_id=job_id, graph=graph_name, thread_id=thread_id,
                                       status="running", trace_id=trace_id, started_at=time.time()))
    channel = f"run:{run_id}"
    cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": 60}
    await events.publish(channel, {"type": "start", "run_id": run_id, "thread_id": thread_id, "graph": graph_name})
    await events.publish(f"user:{user_id}", {"type": "run_started", "run_id": run_id, "job_id": job_id, "graph": graph_name})
    status, error = "done", None
    try:
        async for update_ in graph.astream(inp, cfg, stream_mode="updates"):
            for node_name, upd in update_.items():
                if node_name == "__interrupt__":
                    await events.publish(channel, {"type": "interrupt", "node": "approval"})
                    continue
                entry = ((upd or {}).get("node_log") or [{}])[-1] if isinstance(upd, dict) else {}
                await events.publish(channel, {"type": "node", "node": node_name, "summary": entry.get("summary"),
                                               "latency_s": entry.get("latency_s"), "tokens": entry.get("tokens"),
                                               "model": entry.get("model"), "status": (upd or {}).get("status") if isinstance(upd, dict) else None})
    except ToolUnavailable as e:
        status, error = "waiting_marketplace", str(e)
    except Exception as e:  # retries exhausted inside the graph: dead-letter it
        status, error = "dead_letter", f"{type(e).__name__}: {e}"
        log.exception("run %s failed", run_id)
        with engine().begin() as c:
            c.execute(dead_letter.insert().values(user_id=user_id, job_id=job_id, thread_id=thread_id, error=error[:2000]))
    snap = await graph.aget_state(cfg)
    values = snap.values or {}
    pending = bool(snap.next) and any(t.interrupts for t in snap.tasks)
    if status == "done" and pending:
        status = "awaiting_approval"
    meter_tokens, meter_cost = values.get("tokens", 0), values.get("cost_usd", 0.0)
    with engine().begin() as c:
        c.execute(update(runs).where(runs.c.id == run_id).values(status=status, finished_at=time.time(), error=error,
                                                                 tokens=meter_tokens, cost_usd=meter_cost))
        if pending:
            payload = next(t.interrupts[0].value for t in snap.tasks if t.interrupts)
            c.execute(approvals.delete().where(approvals.c.thread_id == thread_id, approvals.c.status == "pending"))
            c.execute(approvals.insert().values(id=uuid.uuid4().hex[:16], user_id=user_id, thread_id=thread_id, graph=graph_name,
                                                kind=payload.get("kind"), job_id=job_id, payload=payload, status="pending"))
        if graph_name == "bid" and job_id:
            job_status = status if status in ("waiting_marketplace", "dead_letter") else values.get("status") or status
            c.execute(update(jobs).where(jobs.c.user_id == user_id, jobs.c.job_id == job_id).values(
                status=job_status, thread_id=thread_id, summary=_summary_from_state(values), updated_at=time.time(),
                **{k: v for k, v in {"fit": (values.get("fit") or {}).get("fit_score"), "risk": (values.get("risk") or {}).get("risk_score"),
                                     "action": (values.get("decision") or {}).get("action"),
                                     "price": (values.get("price") or {}).get("amount")}.items() if v is not None}))
        if graph_name == "conversation":
            c.execute(update(conversations).where(conversations.c.user_id == user_id, conversations.c.graph_thread == thread_id)
                      .values(status=status if pending or status != "done" else values.get("status", "done"), updated_at=time.time()))
    await events.publish(channel, {"type": "end", "status": status, "error": error, "run_id": run_id})
    await events.publish(f"user:{user_id}", {"type": "run_finished", "run_id": run_id, "job_id": job_id, "status": status})
    return {"run_id": run_id, "status": status, "error": error, "trace_id": trace_id}


async def analyze_job(rt: Runtime, user_id: str, job_id: str) -> dict:
    """Idempotent: only a job in 'queued' (or waiting_marketplace) state is claimed; a worker restart cannot
    double-analyse because the claim is an atomic UPDATE ... WHERE status IN (...)."""
    with engine().begin() as c:
        res = c.execute(update(jobs).where(jobs.c.user_id == user_id, jobs.c.job_id == job_id,
                                           jobs.c.status.in_(["queued", "waiting_marketplace"])).values(status="analysing",
                                                                                                         updated_at=time.time()))
        if res.rowcount == 0:
            return {"status": "already_processed"}
        row = c.execute(select(jobs).where(jobs.c.user_id == user_id, jobs.c.job_id == job_id)).first()
    job = row_dict(row)["data"]
    user = get_user(user_id)
    thread_id = f"{user_id}:{job_id}"
    trace_id = tracing.new_trace_id()
    cfg = {"configurable": {"thread_id": thread_id}}
    snap = await rt.bid.aget_state(cfg)
    inp = None if snap.values else {"user_id": user_id, "persona": user.get("persona") or "ai_ml", "thread_id": thread_id,
                                     "trace_id": trace_id, "job": job, "meta": user_meta(user)}
    return await _stream(rt, rt.bid, "bid", user_id, thread_id, job_id, inp, trace_id)


async def resume(rt: Runtime, user_id: str, thread_id: str, decision: dict | None) -> dict:
    """Resume after a human decision. If the graph is already past the approval (a crash mid-submit), continue
    from the checkpoint instead; idempotency keys make the submit exactly-once either way."""
    with engine().begin() as c:
        appr = c.execute(select(approvals).where(approvals.c.user_id == user_id, approvals.c.thread_id == thread_id)
                         .order_by(approvals.c.created_at.desc())).first()
    graph_name = row_dict(appr)["graph"] if appr else "bid"
    graph = rt.bid if graph_name == "bid" else rt.conversation
    cfg = {"configurable": {"thread_id": thread_id}}
    snap = await graph.aget_state(cfg)
    if not snap.next:
        return {"status": "nothing_to_resume"}
    waiting_on_interrupt = any(t.interrupts for t in snap.tasks)
    inp = Command(resume=decision) if waiting_on_interrupt else None
    trace_id = (snap.values or {}).get("trace_id") or tracing.new_trace_id()
    job_id = ((snap.values or {}).get("job") or {}).get("id")
    out = await _stream(rt, graph, graph_name, user_id, thread_id, job_id, inp, trace_id)
    if out["status"] not in ("waiting_marketplace", "dead_letter"):
        # only now is the decision fully applied; a crash before this line is replayed by recover_decided()
        with engine().begin() as c:
            c.execute(update(approvals).where(approvals.c.user_id == user_id, approvals.c.thread_id == thread_id,
                                              approvals.c.status == "decided").values(status="completed"))
    return out


async def start_conversation(rt: Runtime, user_id: str, thread: dict, new_msg: dict, job: dict | None, proposal: dict | None) -> dict:
    user = get_user(user_id)
    gthread = f"{user_id}:conv:{thread['id']}:{new_msg['id']}"
    with engine().begin() as c:
        c.execute(conversations.delete().where(conversations.c.user_id == user_id, conversations.c.thread_id == thread["id"]))
        c.execute(conversations.insert().values(user_id=user_id, thread_id=thread["id"], job_id=(job or {}).get("id"), data=thread,
                                                status="drafting", last_seen_msg=new_msg["id"], graph_thread=gthread))
    trace_id = tracing.new_trace_id()
    inp = {"user_id": user_id, "persona": user.get("persona") or "ai_ml", "thread_id": thread["id"], "trace_id": trace_id,
           "job": job or {}, "proposal": proposal or {}, "messages": thread.get("messages", []), "new_message": new_msg,
           "meta": user_meta(user)}
    return await _stream(rt, rt.conversation, "conversation", user_id, gthread, (job or {}).get("id"), inp, trace_id)


async def recover_decided(rt: Runtime) -> list[dict]:
    """On worker/API start: finish any approval that was decided but whose run never completed (crash recovery)."""
    with engine().begin() as c:
        rows = [row_dict(r) for r in c.execute(select(approvals).where(approvals.c.status == "decided"))]
    out = []
    for r in rows:
        out.append(await resume(rt, r["user_id"], r["thread_id"], r["decision"]))
    return out
