from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from agent.graphs.conversation_graph import build_conversation_graph


async def _thread(sim, body: str):
    # create a real GigSim thread: submit a proposal, then let the client reply
    job = next(j for j in sim.all_jobs if j["_meta"]["persona"] == "ai_ml" and j["_meta"]["kind"] == "fit")
    d = sim.create_draft("f-ai_ml", job["id"], "My LangGraph agent cut handling time from 9 to 3 minutes. " * 6, job["budget"], [], "k-conv-1")
    p = sim.submit("f-ai_ml", d["id"], "k-conv-2")
    tid = "t-" + p["id"][2:]
    sim.state["threads"][tid] = {"id": tid, "freelancer": "f-ai_ml", "job_id": job["id"], "client_id": job["client_id"],
                                 "proposal_id": p["id"], "awaiting_client": False,
                                 "messages": [{"id": "m1", "from": "client", "body": body, "ts": 0}]}
    return tid, sim.get_job(job["id"]), p


def _init(tid, job, prop, body):
    return {"user_id": "u-test", "persona": "ai_ml", "thread_id": tid, "trace_id": "t", "job": job, "proposal": prop,
            "new_message": {"id": "m1", "body": body}, "meta": {"hourly_floor": 45}}


async def test_interview_request_offers_slots_and_holds_after_approval(gigsim_port):
    body = "This looks promising. Are you available for a short interview call this week?"
    tid, job, prop = await _thread(gigsim_port, body)
    g = build_conversation_graph().compile(checkpointer=InMemorySaver(), store=InMemoryStore())
    cfg = {"configurable": {"thread_id": "c1"}}
    out = await g.ainvoke(_init(tid, job, prop, body), cfg)
    assert out["intent"]["intent"] == "interview_request" and len(out["slots"]) == 3
    out = await g.ainvoke(Command(resume={"action": "approve", "slot": 1}), cfg)
    assert out["status"] == "sent" and out["hold"]["status"] == "tentative"
    assert gigsim_port.state["threads"][tid]["messages"][-1]["from"] == "freelancer"


async def test_scam_signal_reply_keeps_it_on_platform(gigsim_port):
    body = "Let's move to Telegram @hr_777, payment will be in USDT."
    tid, job, prop = await _thread(gigsim_port, body)
    g = build_conversation_graph().compile(checkpointer=InMemorySaver(), store=InMemoryStore())
    out = await g.ainvoke(_init(tid, job, prop, body), {"configurable": {"thread_id": "c2"}})
    assert out["intent"]["intent"] == "scam_signal"
    assert "telegram" not in out["reply"]["body"].lower() and "on the platform" in out["reply"]["body"]


async def test_negotiation_respects_floor(gigsim_port):
    body = "Your rate is a bit above what we planned. Could you do it for $5?"
    tid, job, prop = await _thread(gigsim_port, body)
    g = build_conversation_graph().compile(checkpointer=InMemorySaver(), store=InMemoryStore())
    out = await g.ainvoke(_init(tid, job, prop, body), {"configurable": {"thread_id": "c3"}})
    assert out["intent"]["intent"] == "negotiation" and out["reply"]["walk_away"] is True
