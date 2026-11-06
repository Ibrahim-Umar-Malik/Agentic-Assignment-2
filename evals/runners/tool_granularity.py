"""R&D Question A: how coarse should MCP tools be?

Three designs of the same capabilities:
  * task_shaped  (shipped) - tools named after the agent's tasks: search_evidence, get_client_history, get_market_stats ...
  * fine_grained (API-shaped) - one tool per field / endpoint (22 tools)
  * mega          - one tool per server with an `action` argument
40 tasks (8 templates x 5 entities) each have the set of correct first calls under each design.
Measured: schema size the model must read on every turn, tool-selection accuracy, calls per task, tokens, latency.
Selection accuracy needs a tool-calling LLM; with the offline profile only the schema-size part is measured.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from pydantic import create_model

from .common import mean, run_meta, write_result

STR = (str, ...)
TOOLSETS: dict[str, dict[str, tuple[str, dict[str, Any]]]] = {
    "task_shaped": {
        "search_jobs": ("Search open jobs by keywords, category and skills.", {"query": STR, "category": (str | None, None)}),
        "get_job": ("Full job post: title, description, budget, skills, screening questions.", {"job_id": STR}),
        "get_client_history": ("Client track record: hires, spend, rating, payment verification, reviews.", {"client_id": STR}),
        "get_market_stats": ("Price percentiles of similar awarded jobs.", {"category": STR, "budget_type": STR}),
        "get_connects_balance": ("Connects balance.", {}),
        "search_evidence": ("Portfolio evidence (case studies, repos, past proposals, reviews) for one requirement.", {"requirement": STR}),
        "get_case_study": ("Full text of one case study.", {"id": STR}),
        "list_skills": ("Skills the freelancer can evidence, with counts.", {}),
    },
    "fine_grained": {**{f"get_job_{f}": (f"The job's {f}.", {"job_id": STR}) for f in ("title", "description", "budget", "skills", "questions")},
                     **{f"get_client_{f}": (f"The client's {f}.", {"client_id": STR}) for f in ("rating", "spend", "hires", "payment_status", "reviews")},
                     "search_jobs_by_keyword": ("Search jobs by keyword.", {"keyword": STR}),
                     "search_jobs_by_category": ("Search jobs in a category.", {"category": STR}),
                     "get_price_p25": ("25th percentile price.", {"category": STR}), "get_price_p50": ("Median price.", {"category": STR}),
                     "get_price_p75": ("75th percentile price.", {"category": STR}), "get_connects_balance": ("Connects balance.", {}),
                     "search_case_studies": ("Search case studies.", {"query": STR}), "search_repos": ("Search repositories.", {"query": STR}),
                     "search_past_proposals": ("Search past proposals.", {"query": STR}), "search_reviews": ("Search client reviews.", {"query": STR}),
                     "get_case_study": ("One case study.", {"id": STR}), "list_skills": ("Skills list.", {})},
    "mega": {"marketplace": ("Marketplace. action: search_jobs|get_job|client_history|market_stats|connects. params: object.",
                             {"action": STR, "params": (dict, {})}),
             "portfolio": ("Portfolio. action: search|case_study|skills. params: object.", {"action": STR, "params": (dict, {})})},
}

TEMPLATES = [  # (task, correct first tool per design, minimum calls per design)
    ("Is client {c} trustworthy? Check their history.", {"task_shaped": {"get_client_history"}, "fine_grained": {"get_client_rating", "get_client_reviews", "get_client_payment_status", "get_client_hires", "get_client_spend"}, "mega": {"marketplace"}}, {"task_shaped": 1, "fine_grained": 4, "mega": 1}),
    ("Find my strongest evidence for {s}.", {"task_shaped": {"search_evidence"}, "fine_grained": {"search_case_studies", "search_repos", "search_past_proposals", "search_reviews"}, "mega": {"portfolio"}}, {"task_shaped": 1, "fine_grained": 4, "mega": 1}),
    ("What do similar {k} jobs pay? Give the p25-p75 range.", {"task_shaped": {"get_market_stats"}, "fine_grained": {"get_price_p25", "get_price_p75", "get_price_p50"}, "mega": {"marketplace"}}, {"task_shaped": 1, "fine_grained": 2, "mega": 1}),
    ("Read job {j} and list its screening questions.", {"task_shaped": {"get_job"}, "fine_grained": {"get_job_questions"}, "mega": {"marketplace"}}, {"task_shaped": 1, "fine_grained": 1, "mega": 1}),
    ("Show new jobs about {s}.", {"task_shaped": {"search_jobs"}, "fine_grained": {"search_jobs_by_keyword"}, "mega": {"marketplace"}}, {"task_shaped": 1, "fine_grained": 1, "mega": 1}),
    ("Can I afford to bid on job {j}? Compare its Connects cost with my balance.", {"task_shaped": {"get_job", "get_connects_balance"}, "fine_grained": {"get_job_budget", "get_connects_balance"}, "mega": {"marketplace"}}, {"task_shaped": 2, "fine_grained": 2, "mega": 2}),
    ("Which of my skills could I evidence for a {k} job?", {"task_shaped": {"list_skills"}, "fine_grained": {"list_skills"}, "mega": {"portfolio"}}, {"task_shaped": 1, "fine_grained": 1, "mega": 1}),
    ("Summarise job {j}: budget, skills and what the client really needs.", {"task_shaped": {"get_job"}, "fine_grained": {"get_job_description", "get_job_budget", "get_job_skills", "get_job_title"}, "mega": {"marketplace"}}, {"task_shaped": 1, "fine_grained": 3, "mega": 1}),
]
ENTITIES = [{"c": "c0052", "s": "LangGraph", "k": "llm_apps", "j": "j-ai_ml-004"}, {"c": "c0093", "s": "Django", "k": "fullstack_saas", "j": "j-fullstack-026"},
            {"c": "c0281", "s": "Power BI", "k": "bi_dashboards", "j": "j-data_analyst-057"}, {"c": "c0300", "s": "RAG", "k": "mlops", "j": "j-ai_ml-037"},
            {"c": "c0011", "s": "dbt", "k": "data_engineering", "j": "j-data_analyst-050"}]


def tasks() -> list[dict]:
    return [{"task": t.format(**e), "first": first, "min_calls": mc} for t, first, mc in TEMPLATES for e in ENTITIES]


def lc_tools(design: str):
    from langchain_core.tools import StructuredTool

    out = []
    for name, (desc, fields) in TOOLSETS[design].items():
        schema = create_model(f"{design}_{name}_args", **fields) if fields else create_model(f"{design}_{name}_args")

        async def _run(_n=name, **kw):
            return json.dumps({"tool": _n, "ok": True})

        out.append(StructuredTool.from_function(coroutine=_run, name=name, description=desc, args_schema=schema))
    return out


def schema_chars(design: str) -> int:
    from langchain_core.utils.function_calling import convert_to_openai_tool

    return sum(len(json.dumps(convert_to_openai_tool(t))) for t in lc_tools(design))


async def selection(design: str, ts: list[dict]) -> dict:
    from core import llm

    model = llm._chat_model(llm.model_for("analyst")).bind_tools(lc_tools(design))
    correct, lat, toks = [], [], []
    for t in ts:
        s = time.perf_counter()
        msg = await model.ainvoke([("system", "Use the tools to do the task. Call the single best tool first."), ("user", t["task"])])
        lat.append(time.perf_counter() - s)
        um = getattr(msg, "usage_metadata", None) or {}
        toks.append(um.get("total_tokens", 0))
        first = (msg.tool_calls or [{}])[0].get("name")
        correct.append(float(first in t["first"][design]))
    return {"selection_accuracy": mean(correct), "mean_tokens_first_turn": mean(toks), "mean_latency_s": mean(lat)}


async def main_async() -> dict:
    from core import llm

    ts = tasks()
    out: dict[str, Any] = {}
    for design in TOOLSETS:
        chars = schema_chars(design)
        out[design] = {"tools": len(TOOLSETS[design]), "schema_chars": chars, "schema_tokens_approx": round(chars / 4),
                       "min_calls_per_task": mean([t["min_calls"][design] for t in ts])}
        if not llm.is_offline("analyst"):
            out[design].update(await selection(design, ts))
        else:
            out[design]["selection_accuracy"] = {"status": "not_run", "reason": "needs a tool-calling LLM (offline profile)"}
    return {"n_tasks": len(ts), "designs": out}


def main() -> None:
    logging.disable(logging.INFO)
    res = asyncio.run(main_async())
    write_result("tool_granularity", {"meta": run_meta(token_estimate="OpenAI tool-schema JSON chars / 4"), **res})
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
