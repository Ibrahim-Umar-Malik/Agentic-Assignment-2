"""Export four public execution traces to docs/traces/*.json (the same span data the live app serves at
/share/trace/<id>): a skipped scam, an approved proposal, a Critic loop and a crash-and-resume.

    GIGBID_PROFILE=offline python scripts/export_traces.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="gigbid-traces-"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TMP / 'traces.db'}")
os.environ.setdefault("GIGSIM_STATE", str(TMP / "gigsim.json"))
os.environ.setdefault("GIGSIM_ERROR_RATE", "0")
os.environ["GIGBID_MCP_INPROCESS"] = "1"
os.environ["MARKETPLACE_ALLOW_ANON"] = "1"
OUT = ROOT / "docs" / "traces"


def spans(trace_id: str) -> list[dict]:
    from sqlalchemy import select

    from core.db import engine, row_dict, trace_spans

    with engine().begin() as c:
        rows = [row_dict(r) for r in c.execute(select(trace_spans).where(trace_spans.c.trace_id == trace_id).order_by(trace_spans.c.start))]
    t0 = rows[0]["start"] if rows else 0
    return [{"name": r["name"], "kind": r["kind"], "t_start_s": round(r["start"] - t0, 4), "duration_s": round(r["end"] - r["start"], 4),
             "attrs": r["attrs"]} for r in rows]


def dump(name: str, trace_id: str, title: str, state: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    s = spans(trace_id)
    doc = {"title": title, "trace_id": trace_id, "profile": os.environ.get("GIGBID_PROFILE", "offline"),
           "job": {k: state.get("job", {}).get(k) for k in ("id", "title", "budget", "budget_type", "connects_cost")},
           "outcome": {"status": state.get("status"), "reason": state.get("status_reason"), "decision": (state.get("decision") or {}).get("action"),
                       "submission": state.get("submission"), "critiques": len(state.get("critiques") or [])},
           "node_path": [n["node"] for n in state.get("node_log") or []], "spans": s}
    (OUT / f"{name}.json").write_text(json.dumps(doc, indent=1, default=str))
    print(f"{name}: {len(s)} spans, path {' > '.join(doc['node_path'])}")


async def main() -> None:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from langgraph.store.memory import InMemoryStore
    from langgraph.types import Command

    from agent.graphs.bid_graph import build_bid_graph
    from core import config
    from core.db import init_db
    from gigsim_standin.app import sim
    from mcp_servers.marketplace import server
    from tests.fakes import gigsim_adapter

    init_db()
    sim.reset()
    server._port_override = gigsim_adapter("dev-ai_ml")

    def job(kind: str, n: int = 0) -> dict:
        js = [j for j in sim.all_jobs if j["_meta"]["persona"] == "ai_ml" and j["_meta"].get("kind") == kind
              and (kind == "scam" or sim.clients[j["client_id"]].get("payment_verified"))]
        return sim.get_job(js[n]["id"])

    def init(j: dict, tid: str) -> dict:
        return {"user_id": "u-demo", "persona": "ai_ml", "thread_id": tid, "trace_id": tid, "job": j, "meta": {"hourly_floor": 40}}

    g = build_bid_graph().compile(checkpointer=InMemorySaver(), store=InMemoryStore())
    out = await g.ainvoke(init(job("scam"), "trace-scam-skipped"), {"configurable": {"thread_id": "trace-scam-skipped"}})
    dump("scam_skipped", "trace-scam-skipped", "Scam post skipped before any writing", out)

    cfg = {"configurable": {"thread_id": "trace-approved"}}
    await g.ainvoke(init(job("fit", 0), "trace-approved"), cfg)
    out = await g.ainvoke(Command(resume={"action": "approve", "by": "reviewer"}), cfg)
    dump("approved_proposal", "trace-approved", "Job to approved, submitted proposal", out)

    os.environ["GIGBID_CONFIG_OVERRIDES"] = json.dumps({"critic": {"min_score": 1.01}})
    config.reload_config()
    out = await g.ainvoke(init(job("fit", 2), "trace-critic-loop"), {"configurable": {"thread_id": "trace-critic-loop"}})
    os.environ.pop("GIGBID_CONFIG_OVERRIDES")
    config.reload_config()
    dump("critic_loop", "trace-critic-loop", "Critic sends the draft back; the loop stops at critic.max_revisions", out)

    cfg = {"configurable": {"thread_id": "trace-crash-resume"}}
    db = str(TMP / "cp.db")
    async with AsyncSqliteSaver.from_conn_string(db) as cp:
        await build_bid_graph().compile(checkpointer=cp, store=InMemoryStore()).ainvoke(init(job("fit", 1), "trace-crash-resume"), cfg)
    # process "dies" here; a new process opens the same checkpoint database and resumes after approval
    async with AsyncSqliteSaver.from_conn_string(db) as cp2:
        g2 = build_bid_graph().compile(checkpointer=cp2, store=InMemoryStore())
        out = await g2.ainvoke(Command(resume={"action": "approve", "by": "reviewer"}), cfg)
        hist = [s async for s in g2.aget_state_history(cfg)]
        replay = await g2.ainvoke(None, next(s for s in hist if s.next == ("submit",)).config)  # crashed worker re-runs submit
        out["submission"] = {**out["submission"], "replay_after_crash": replay["submission"]}
    dump("crash_resume", "trace-crash-resume", "Crash after approval: resumed from the checkpoint, submitted exactly once", out)
    server._port_override = None


if __name__ == "__main__":
    import logging

    logging.disable(logging.INFO)
    asyncio.run(main())
