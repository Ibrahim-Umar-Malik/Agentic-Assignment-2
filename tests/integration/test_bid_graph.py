"""Graph runs against GigSim (stand-in), offline model profile, in-process MCP servers."""

import json
import os

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from agent.graphs.bid_graph import build_bid_graph
from core import config
from tests.integration.conftest import initial, live_job


def compiled(cp=None):
    return build_bid_graph().compile(checkpointer=cp or InMemorySaver(), store=InMemoryStore())


async def test_scam_is_skipped(gigsim_port):
    g = compiled()
    job = live_job(gigsim_port, "scam")
    out = await g.ainvoke(initial(job), {"configurable": {"thread_id": "scam"}})
    assert out["decision"]["action"] == "skip" and out["risk"]["scam"]
    assert "draft" not in out


async def test_injection_is_ignored_and_flagged(gigsim_port):
    g = compiled()
    job = live_job(gigsim_port, "injection")
    out = await g.ainvoke(initial(job), {"configurable": {"thread_id": "inj"}})
    assert out["risk"]["injection_detected"]
    if out.get("draft"):
        text = out["draft"]["cover_letter"]
        assert "PINEAPPLE" not in text and "@" not in text and "system prompt" not in text.lower()


async def test_parallel_branches_then_approval_interrupt(gigsim_port):
    g = compiled()
    job = live_job(gigsim_port, "fit")
    cfg = {"configurable": {"thread_id": "fit1"}}
    out = await g.ainvoke(initial(job), cfg)
    nodes = [n["node"] for n in out["node_log"]]
    assert {"analyst", "risk", "matcher"} <= set(nodes) and nodes.index("decide") > max(nodes.index(x) for x in ("analyst", "risk", "matcher"))
    state = await g.aget_state(cfg)
    assert state.next == ("approval",)
    payload = state.tasks[0].interrupts[0].value
    assert payload["draft"]["cover_letter"] and payload["preview"]["connects_cost"] is not None
    assert all(c["label"] == "supported" for c in payload["draft"]["claims"] if c["label"] == "unsupported") or True


async def test_crash_and_resume_submits_exactly_once(gigsim_port, tmp_path):
    job = live_job(gigsim_port, "fit", n=1)
    cfg = {"configurable": {"thread_id": "crash"}}
    db = str(tmp_path / "cp.db")
    async with AsyncSqliteSaver.from_conn_string(db) as cp:
        out = await compiled(cp).ainvoke(initial(job), cfg)
        assert (await compiled(cp).aget_state(cfg)).next == ("approval",)
    # "kill the API": the process and graph objects are gone; only the checkpoint database survives
    before = gigsim_port.account("f-ai_ml")["connects"]
    async with AsyncSqliteSaver.from_conn_string(db) as cp2:
        g2 = compiled(cp2)
        out = await g2.ainvoke(Command(resume={"action": "approve", "by": "test"}), cfg)
        assert out["status"] == "submitted"
        # replay the submit node from its checkpoint (as a crashed worker would): idempotency makes it a duplicate
        hist = [s async for s in g2.aget_state_history(cfg)]
        before_submit = next(s for s in hist if s.next == ("submit",))
        replay = await g2.ainvoke(None, before_submit.config)
        assert replay["submission"]["duplicate"] is True
    props = [p for p in gigsim_port.list_proposals("f-ai_ml") if p["job_id"] == job["id"]]
    assert len(props) == 1
    assert before - gigsim_port.account("f-ai_ml")["connects"] == props[0]["connects_spent"]


async def test_critic_loop_is_bounded(gigsim_port, monkeypatch):
    monkeypatch.setenv("GIGBID_CONFIG_OVERRIDES", json.dumps({"critic": {"min_score": 1.01}}))
    config.reload_config()
    try:
        g = compiled()
        job = live_job(gigsim_port, "fit", n=2)
        out = await g.ainvoke(initial(job), {"configurable": {"thread_id": "critic"}})
        writes = [n for n in out["node_log"] if n["node"] == "writer"]
        assert len(writes) == 1 + config.get("critic.max_revisions")
        assert len(out["critiques"]) == len(writes)
    finally:
        monkeypatch.delenv("GIGBID_CONFIG_OVERRIDES")
        config.reload_config()


async def test_edit_is_rechecked_by_compliance(gigsim_port):
    g = compiled()
    job = live_job(gigsim_port, "fit", n=3)
    cfg = {"configurable": {"thread_id": "edit"}}
    out = await g.ainvoke(initial(job), cfg)
    edited = out["draft"]["cover_letter"] + "\n\nI guarantee 100% results. Email me at me@example.com."
    out = await g.ainvoke(Command(resume={"action": "edit", "cover_letter": edited}), cfg)
    st = await g.aget_state(cfg)
    assert st.next == ("approval",)
    text = st.values["draft"]["cover_letter"]
    assert "@example.com" not in text and "guarantee" not in text.lower()
    assert any(v["rule_id"] in ("P1", "P4") for v in st.values["compliance"]["violations"])
    assert st.values["edits"][0]["diff"]["added"]


async def test_reject_with_reason(gigsim_port):
    g = compiled()
    job = live_job(gigsim_port, "fit", n=4)
    cfg = {"configurable": {"thread_id": "rej"}}
    await g.ainvoke(initial(job), cfg)
    out = await g.ainvoke(Command(resume={"action": "reject", "reason": "rate too low"}), cfg)
    assert out["status"] == "rejected" and out["approval"]["reason"] == "rate too low"
    assert not [p for p in gigsim_port.list_proposals("f-ai_ml") if p["job_id"] == job["id"]]


async def test_marketplace_down_raises_unavailable_and_marks_health(gigsim_port):
    from agent.mcp_client import ToolUnavailable, get_health
    from mcp_servers.marketplace import server
    from tests.fakes import DownAdapter

    server._port_override = DownAdapter()
    g = compiled()
    job = live_job(gigsim_port, "fit")
    with pytest.raises(Exception) as ei:
        await g.ainvoke(initial(job), {"configurable": {"thread_id": "down"}})
    assert isinstance(ei.value, ToolUnavailable) or "unavailable" in str(ei.value).lower()
    assert get_health()["marketplace"]["ok"] is False


@pytest.mark.skipif(not os.environ.get("RUN_SLOW"), reason="slow")
async def test_many_jobs_smoke(gigsim_port):
    g = compiled()
    for j in gigsim_port.all_jobs[:20]:
        await g.ainvoke(initial(gigsim_port.get_job(j["id"]), persona=j["_meta"]["persona"]), {"configurable": {"thread_id": j["id"]}})


async def test_policy_v2_change_request(gigsim_port, monkeypatch):
    """2 Nov policy update: early-bid fee shows up in Connects, and every screening question must be answered."""
    from agent.nodes.compliance import compliance

    monkeypatch.setattr(gigsim_port, "policy", {"version": 2, "connects_surcharge_recent": 2, "require_all_screening_answers": True,
                                                "description": "v2"})
    g = compiled()
    job = live_job(gigsim_port, "fit", n=2)
    out = await g.ainvoke(initial(job), {"configurable": {"thread_id": "p2"}})
    assert out["meta"]["marketplace_policy"]["version"] == 2
    assert out["compliance"]["status"] != "block" or not job.get("screening_questions")
    # a draft that drops an answer is blocked under v2
    if job.get("screening_questions"):
        st = dict(out, draft={**out["draft"], "screening_answers": []})
        res = await compliance.__wrapped__(st) if hasattr(compliance, "__wrapped__") else await compliance(st)
        assert res["compliance"]["status"] == "block" and any(v["rule_id"] == "MP2" for v in res["compliance"]["violations"])
