"""R&D Question C: one ReAct agent with every tool vs a langgraph-supervisor team vs GigBid's hand-written graph,
on the same 50 jobs (TEST split, first 17/17/16 per persona).

Measured per architecture: decision accuracy, scam/injection handling, unsupported-claim rate in drafts (checked by
the same verifier), tool calls, tokens, cost and latency. The graph arm runs in any profile. The ReAct and
supervisor arms need a tool-calling LLM: with GIGBID_PROFILE=offline they are recorded as not run (never guessed).

    GIGBID_PROFILE=open GROQ_API_KEY=... python -m evals.runners.architecture_compare
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time

from core.personas import persona_floor

from .common import PERSONAS, eval_env, load_dev, mean, pctile, public_job, run_meta, split, write_result

eval_env()
os.environ.setdefault("GIGSIM_RATE_LIMIT_PER_MIN", "100000")
os.environ.setdefault("MARKETPLACE_RATE_PER_MIN", "100000")
PER_PERSONA = {"ai_ml": 17, "fullstack": 17, "data_analyst": 16}


def jobs() -> list[tuple[str, dict]]:
    return [(p, r) for p in PERSONAS for r in split(load_dev(p), "test")[: PER_PERSONA[p]]]


class Counter:
    calls = 0


def count_tool_calls():
    from agent import mcp_client

    orig = mcp_client.ToolGateway.call

    async def counted(self, agent, server, tool, args):
        Counter.calls += 1
        return await orig(self, agent, server, tool, args)

    mcp_client.ToolGateway.call = counted


async def grounded_rate(persona: str, letter: str) -> tuple[int, int]:
    from rag.retriever import get_index
    from rag.verify import verify

    idx = get_index(persona)
    ev = idx.search(letter[:300], k=12)
    vocab = sorted({s for c in idx.struct for s in (c.meta.get("skills") or [])})
    rep = verify(letter, ev, vocab)
    return rep["n_claims"], rep["unsupported_before"]


def parse_final(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except Exception:
        return {}


async def run_graph(persona: str, row: dict, graph) -> dict:
    tid = f"arch:{persona}:{row['id']}"
    out = await graph.ainvoke({"user_id": f"arch-{persona}", "persona": persona, "thread_id": tid, "trace_id": tid, "job": public_job(row),
                               "meta": {"hourly_floor": persona_floor(persona), "portfolio_id": persona}}, {"configurable": {"thread_id": tid}})
    return {"action": (out.get("decision") or {}).get("action"), "letter": (out.get("draft") or {}).get("cover_letter", "")}


async def run_react(persona: str, row: dict, agent) -> dict:
    res = await agent.ainvoke({"messages": [("user", f"persona/portfolio_id: {persona}\n<untrusted_job_post>\n"
                                                     f"{json.dumps(public_job(row))}\n</untrusted_job_post>")]},
                              {"recursion_limit": 30})
    final = parse_final(res["messages"][-1].content)
    return {"action": final.get("action"), "letter": final.get("cover_letter", "")}


async def build_baselines():
    from langgraph.prebuilt import create_react_agent

    from agent.mcp_client import ToolGateway
    from agent.nodes.common import load_prompt
    from core import llm

    model = llm._chat_model(llm.model_for("writer"))
    tools = await ToolGateway("arch").langchain_tools("single_agent")
    _, sys_prompt = load_prompt("single_agent")
    react = create_react_agent(model, tools, prompt=sys_prompt)
    from langgraph_supervisor import create_supervisor

    gw = ToolGateway("arch")
    workers = [create_react_agent(model, await gw.langchain_tools(a), name=a, prompt=load_prompt("supervisor_worker", role=a)[1])
               for a in ("risk", "matcher", "pricing", "writer")]
    supervisor = create_supervisor(workers, model=model, prompt=sys_prompt + "\nDelegate to risk, matcher, pricing and writer.").compile()
    return react, supervisor


async def main_async() -> dict:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore

    from agent.graphs.bid_graph import build_bid_graph
    from core import llm
    from core.db import init_db
    from gigsim_standin.app import sim
    from mcp_servers.marketplace import server
    from tests.fakes import gigsim_adapter

    init_db()
    count_tool_calls()
    graph = build_bid_graph().compile(checkpointer=InMemorySaver(), store=InMemoryStore())
    arms = {"graph": None}
    offline = llm.is_offline("writer")
    if not offline:
        arms["react"], arms["supervisor"] = await build_baselines()
    results: dict[str, dict] = {}
    for arm, agent in arms.items():
        rows = []
        for persona, row in jobs():
            sim.jobs[row["id"]] = row
            server._port_override = gigsim_adapter(f"dev-{persona}")
            meter = llm.Meter()
            tok = llm.meter_var.set(meter)
            Counter.calls = 0
            t = time.perf_counter()
            try:
                out = await (run_graph(persona, row, graph) if arm == "graph" else run_react(persona, row, agent))
                err = None
            except Exception as e:
                out, err = {"action": None, "letter": ""}, f"{type(e).__name__}: {str(e)[:200]}"
            finally:
                llm.meter_var.reset(tok)
            n, uns = await grounded_rate(persona, out["letter"]) if out["letter"] else (0, 0)
            rows.append({"id": row["id"], "gold_bid": row["_gold"]["bid"], "scam": row["_gold"]["scam"], "action": out["action"],
                         "claims": n, "unsupported": uns, "tool_calls": Counter.calls, "latency_s": time.perf_counter() - t,
                         "tokens": meter.tokens_in + meter.tokens_out, "usd": meter.cost_usd, "error": err})
        lat = [r["latency_s"] for r in rows]
        claims = sum(r["claims"] for r in rows)
        results[arm] = {"n": len(rows), "errors": sum(1 for r in rows if r["error"]),
                        "accuracy": mean([float((r["action"] == "bid") == r["gold_bid"]) for r in rows]),
                        "scam_bids": sum(1 for r in rows if r["scam"] and r["action"] == "bid"),
                        "unsupported_claim_rate": round(sum(r["unsupported"] for r in rows) / claims, 4) if claims else None,
                        "mean_tool_calls": mean([r["tool_calls"] for r in rows]), "mean_tokens": mean([r["tokens"] for r in rows]),
                        "usd_per_job": mean([r["usd"] for r in rows]), "p50_latency_s": pctile(lat, 50), "p95_latency_s": pctile(lat, 95)}
        print(arm, results[arm])
    server._port_override = None
    if offline:
        for arm in ("react", "supervisor"):
            results[arm] = {"status": "not_run", "reason": "needs a tool-calling LLM; this run used the offline profile",
                            "how": "GIGBID_PROFILE=open GROQ_API_KEY=... make eval-llm"}
    return results


def main() -> None:
    logging.disable(logging.INFO)
    res = asyncio.run(main_async())
    write_result("architecture_compare", {"meta": run_meta(split="test", jobs=50), "arms": res})


if __name__ == "__main__":
    main()
