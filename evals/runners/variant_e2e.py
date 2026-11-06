"""B5 results table: the naive baseline (V0) and the shipped pipeline run END TO END through the bid graph on the
TEST split, so retrieval quality can be compared with what it buys downstream: unsupported claims per proposal,
judge score, GigSim reply rate, p95 latency and cost per proposal.

Hypothesis (written before running): requirement decomposition + reranking raises evidence Recall@5 over V0 and,
through better-grounded drafts, raises the GigSim reply rate by at least 3 points.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from .common import PERSONAS, eval_env, load_dev, mean, pctile, public_job, run_meta, split, write_result

eval_env()
os.environ.setdefault("GIGSIM_RATE_LIMIT_PER_MIN", "100000")
os.environ.setdefault("MARKETPLACE_RATE_PER_MIN", "100000")


async def run_variant(spec: str) -> dict:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore

    from agent.graphs.bid_graph import build_bid_graph
    from core import config, llm
    from core.db import init_db
    from gigsim_standin.app import sim
    from mcp_servers.marketplace import server
    from tests.fakes import gigsim_adapter

    from .gigsim_outcomes import expected
    from .judge_calibration import heuristic_judge, llm_judge

    os.environ["GIGBID_RAG_VARIANT"] = spec
    config.reload_config()
    init_db()
    graph = build_bid_graph().compile(checkpointer=InMemorySaver(), store=InMemoryStore())
    per_job, by_kind = [], {}
    for persona in PERSONAS:
        sim.reset()
        server._port_override = gigsim_adapter(f"dev-{persona}")
        for row in split(load_dev(persona), "test"):
            sim.jobs[row["id"]] = row
            tid = f"ve:{spec}:{row['id']}"
            meter = llm.Meter()
            tok = llm.meter_var.set(meter)
            t = time.perf_counter()
            out = await graph.ainvoke({"user_id": f"ve-{persona}", "persona": persona, "thread_id": tid, "trace_id": tid,
                                       "job": public_job(row), "meta": {"hourly_floor": 40, "portfolio_id": persona}},
                                      {"configurable": {"thread_id": tid}})
            llm.meter_var.reset(tok)
            dt = time.perf_counter() - t
            d = out.get("draft")
            rec = {"kind": row["_gold"]["kind"], "latency_s": dt, "usd": meter.cost_usd, "proposal": bool(d)}
            if d and (out.get("decision") or {}).get("action") == "bid":
                ver = out.get("verification") or {}
                e = expected(sim, row, d["cover_letter"], out["price"]["amount"], [a["answer"] for a in d.get("screening_answers", [])], tid)
                js = await llm_judge(public_job(row), d["cover_letter"]) if not llm.is_offline("judge") else heuristic_judge(public_job(row), d["cover_letter"])
                rec.update(unsupported_before=ver.get("unsupported_before", 0), unsupported_after=ver.get("unsupported_after", 0),
                           p_reply=e["p_reply"], judge=js.overall)
            per_job.append(rec)
    server._port_override = None
    props = [r for r in per_job if "p_reply" in r]
    for k in sorted({r["kind"] for r in props}):
        g = [r for r in props if r["kind"] == k]
        by_kind[k] = {"n": len(g), "reply_rate": mean([r["p_reply"] for r in g])}
    lat = [r["latency_s"] for r in per_job]
    return {"variant": spec, "jobs": len(per_job), "proposals": len(props),
            "unsupported_claims_per_proposal_before_verify": mean([r["unsupported_before"] for r in props]),
            "unsupported_claims_per_proposal": mean([r["unsupported_after"] for r in props]),
            "judge_score": mean([r["judge"] for r in props]), "gigsim_reply_rate": mean([r["p_reply"] for r in props]),
            "p95_latency_s": round(pctile(lat, 95) or 0, 3), "usd_per_proposal": round(sum(r["usd"] for r in per_job) / len(props), 6) if props else None,
            "by_job_kind": by_kind}


def main() -> None:
    logging.disable(logging.INFO)
    rag = json.loads((__import__("pathlib").Path(__file__).resolve().parents[1] / "results" / "rag.json").read_text())
    rows = {}
    for spec in ("v0_naive", rag["chosen"]):
        rows[spec] = asyncio.run(run_variant(spec))
        rows[spec]["recall@5"] = (rag["test"]["baseline_v0"] if spec == "v0_naive" else rag["test"]["chosen"])["recall@5"]
        rows[spec]["ndcg@10"] = (rag["test"]["baseline_v0"] if spec == "v0_naive" else rag["test"]["chosen"]).get("ndcg@10")
        print(spec, {k: v for k, v in rows[spec].items() if k != "by_job_kind"})
    os.environ.pop("GIGBID_RAG_VARIANT", None)
    write_result("variant_e2e", {"meta": run_meta(split="test"), "hypothesis": __doc__.split("Hypothesis (written before running): ")[1].strip(),
                                 "rows": rows})


if __name__ == "__main__":
    main()
