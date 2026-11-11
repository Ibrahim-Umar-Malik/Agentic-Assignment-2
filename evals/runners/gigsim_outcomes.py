"""GigSim outcomes (Part C) and the X2 A/B experiment, on the TEST split of the dev set.

Systems compared on the same jobs, scored by the GigSim client model (hidden preferences, never seen by the agent):
  * gigbid            the shipped graph: decides bid/skip, writes a grounded draft, prices it
  * template_all      a common baseline: bid on every payment-verified job with a generic template at the client's budget
  * reuse_best_past   bid on every job, re-using the freelancer's past proposal that got the best outcome
Reported: bids, Connects spent, expected replies (sum of the simulator's reply probabilities, which removes dice noise),
replies per 100 Connects, expected interviews and hires, and bids on scam posts.

X2 (proposal A/B): for every job GigBid bids on, the Writer is run in BOTH arms (statement: no question, close with a next step;
question: one specific clarifying question); the paired difference in expected reply probability is reported with a bootstrap CI, and a simulated
randomised experiment shows how many proposals per arm the live z-test needs before it can call a winner.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import random

from core.personas import persona_floor

from .common import (
    PERSONAS,
    ROOT,
    bootstrap_ci,
    eval_env,
    load_dev,
    mean,
    public_job,
    run_meta,
    split,
    write_result,
)

eval_env()
os.environ.setdefault("GIGSIM_RATE_LIMIT_PER_MIN", "100000")
os.environ.setdefault("MARKETPLACE_RATE_PER_MIN", "100000")

GENERIC = ("Dear Hiring Manager, I am a passionate and hardworking professional with many years of experience. "
           "I have read your job post carefully and I am the perfect fit for this job. I have worked with {skills}. "
           "I can start immediately and deliver high quality work on time. Looking forward to hearing from you.")


def expected(sim, row: dict, letter: str, bid: float, answers: list[str] | None, key: str) -> dict:
    client = sim.clients[row["client_id"]]
    d = sim.decide(row, client, letter, bid, answers, key)
    p_interview = d["p_reply"] * (0.45 + 0.1 * d["score"])
    p_hire = p_interview * (0.35 + 0.08 * d["score"])
    scam = bool(client.get("_hidden", {}).get("scam"))
    return {"p_reply": 0.0 if scam else d["p_reply"], "p_interview": 0.0 if scam else max(0, min(1, p_interview)),
            "p_hire": 0.0 if scam else max(0, min(1, p_hire)), "scam": scam, "score": d["score"], "reasons": d["reasons"]}


def best_past(persona: str) -> str:
    rank = {"hired": 3, "interview": 2, "replied": 1}
    props = [json.loads(x) for x in (ROOT / "data" / "personas" / persona / "proposals.jsonl").read_text().splitlines() if x.strip()]
    return max(props, key=lambda p: rank.get(p.get("outcome"), 0))["text"]


def agg(rows: list[dict]) -> dict:
    bids = [r for r in rows if r["bid"]]
    connects = sum(r["connects"] for r in bids)
    er = sum(r["p_reply"] for r in bids)
    return {"jobs": len(rows), "bids": len(bids), "connects": connects, "expected_replies": round(er, 2),
            "reply_rate": round(er / len(bids), 4) if bids else None,
            "replies_per_100_connects": round(100 * er / connects, 2) if connects else None,
            "expected_interviews": round(sum(r["p_interview"] for r in bids), 2),
            "expected_hires": round(sum(r["p_hire"] for r in bids), 2), "scam_bids": sum(1 for r in bids if r["scam"])}


async def main_async() -> dict:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore

    from agent.graphs.bid_graph import build_bid_graph
    from agent.nodes.writer import heuristic_draft
    from core.db import init_db
    from gigsim_standin.app import sim
    from mcp_servers.marketplace import server
    from tests.fakes import gigsim_adapter

    init_db()
    graph = build_bid_graph().compile(checkpointer=InMemorySaver(), store=InMemoryStore())
    systems: dict[str, list[dict]] = {"gigbid": [], "template_all": [], "reuse_best_past": []}
    paired: list[dict] = []
    for persona in PERSONAS:
        sim.reset()
        server._port_override = gigsim_adapter(f"dev-{persona}")
        past = best_past(persona)
        for row in split(load_dev(persona), "test"):
            sim.jobs[row["id"]] = row
            job = public_job(row)
            budget = float(row.get("budget") or 0)
            cost = int(row.get("connects_cost") or 0)
            verified = sim.clients[row["client_id"]].get("payment_verified")
            tid = f"oc:{persona}:{row['id']}"
            out = await graph.ainvoke({"user_id": f"eval-{persona}", "persona": persona, "thread_id": tid, "trace_id": tid, "job": job,
                                       "meta": {"hourly_floor": persona_floor(persona), "portfolio_id": persona}}, {"configurable": {"thread_id": tid}})
            bid = (out.get("decision") or {}).get("action") == "bid" and bool(out.get("draft"))
            if bid:
                d, price = out["draft"], out["price"]["amount"]
                e = expected(sim, row, d["cover_letter"], price, [a["answer"] for a in d.get("screening_answers", [])], tid)
                # X2: same job, same evidence, both arms of the opening experiment
                arms = {}
                for arm in ("statement", "question"):
                    st = copy.deepcopy(out)
                    st["meta"] = {**(st.get("meta") or {}), "experiment_arm": arm}
                    letter = heuristic_draft(st, [], [], 1).cover_letter
                    arms[arm] = expected(sim, row, letter, price, None, tid)["p_reply"]
                paired.append({"id": row["id"], "persona": persona, **arms, "diff": arms["question"] - arms["statement"]})
            else:
                e = {"p_reply": 0, "p_interview": 0, "p_hire": 0, "scam": False}
            systems["gigbid"].append({"bid": bid, "connects": cost, **e})
            t = expected(sim, row, GENERIC.format(skills=", ".join(job.get("skills") or [])), budget, None, tid + "t")
            systems["template_all"].append({"bid": bool(verified), "connects": cost, **t})
            r = expected(sim, row, past, budget * 0.95, None, tid + "r")
            systems["reuse_best_past"].append({"bid": True, "connects": cost, **r})
        print(persona, "done")
    server._port_override = None
    diffs = [p["diff"] for p in paired]
    # simulated randomised experiment: how many proposals per arm before the live z-test separates the arms
    from agent.experiments import two_proportion

    rng = random.Random(4016)
    detect = {}
    for n in (30, 60, 120, 250, 500):
        wins = 0
        for _ in range(200):
            sa = sum(rng.random() < rng.choice(paired)["statement"] for _ in range(n))
            sb = sum(rng.random() < rng.choice(paired)["question"] for _ in range(n))
            res = two_proportion(sa, n, sb, n)
            wins += res["p_value"] is not None and res["p_value"] < 0.05
        detect[str(n)] = round(wins / 200, 3)
    return {"systems": {k: agg(v) for k, v in systems.items()},
            "ab_experiment": {"n_jobs": len(paired), "reply_prob_statement": mean([p["statement"] for p in paired]),
                           "reply_prob_question": mean([p["question"] for p in paired]), "paired_diff_question_minus_statement": mean(diffs),
                           "paired_diff_ci95": bootstrap_ci(diffs), "share_jobs_question_better": mean([float(d > 0) for d in diffs]),
                           "power_by_n_per_arm": detect,
                           "by_persona": {p: mean([x["diff"] for x in paired if x["persona"] == p]) for p in PERSONAS}}}


def main() -> None:
    logging.disable(logging.INFO)
    res = asyncio.run(main_async())
    write_result("gigsim_outcomes", {"meta": run_meta(split="test", scoring="expected values from the GigSim client model"), **res})
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
