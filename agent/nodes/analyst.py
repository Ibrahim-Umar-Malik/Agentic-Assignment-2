"""Job Analyst: extract a structured JobSpec (no MCP access)."""

from __future__ import annotations

import re

from core import llm
from rag.index.skills import ALIASES, find_skills

from ..handoffs import JobSpec, Requirement
from .common import load_prompt, node, sanitize_untrusted, wrap

HIDDEN_NEEDS = [
    (r"(?i)previous (contractor|developer|freelancer) (left|quit|disappeared)|half-finished", "reliability and a clean handover"),
    (r"(?i)deadline|urgent|asap|fast", "speed and a clear plan for the deadline"),
    (r"(?i)long-term|ongoing", "availability for ongoing work"),
    (r"(?i)frustrated|slow|manual", "visible quick wins early in the engagement"),
    (r"(?i)does not scale|scal", "a design that scales"),
    (r"(?i)open to ideas|not sure|think .* could help", "advice on what to build, not just execution"),
]


def heuristic_spec(job: dict) -> JobSpec:
    text = f"{job.get('title', '')}. {job.get('description', '')}"
    vocab = list(ALIASES) + list(job.get("skills") or [])
    skills = list(dict.fromkeys((job.get("skills") or []) + find_skills(text, vocab)))
    deliver = re.search(r"(?i)deliverables?:\s*([^.]+)", text)
    timeline = re.search(r"(?i)timeline:\s*([^.]+)|(\d+\s*(weeks?|days?|months?))", text)
    reqs = [Requirement(text=s, skill=s) for s in skills]
    if not reqs:
        sents = [s for s in re.split(r"(?<=[.!?])\s+", job.get("description", "")) if len(s.split()) > 4][:3]
        reqs = [Requirement(text=s, must_have=False) for s in sents]
    return JobSpec(job_id=job["id"], title=job.get("title", ""), category=job.get("category"),
                   deliverables=[d.strip() for d in deliver.group(1).split(",")] if deliver else [],
                   requirements=reqs, budget_type=job.get("budget_type"), budget=job.get("budget"),
                   timeline=(timeline.group(1) or timeline.group(2)).strip() if timeline else None,
                   screening_questions=job.get("screening_questions") or [],
                   hidden_needs=[need for pat, need in HIDDEN_NEEDS if re.search(pat, text)],
                   vague=not job.get("skills") and len(skills) <= 2)


@node("analyst")
async def analyst(state: dict) -> dict:
    job = state["job"]
    base = heuristic_spec(job)
    if not llm.is_offline("analyst"):
        clean, _ = sanitize_untrusted(job.get("description", ""))
        _, system = load_prompt("analyst")
        user = wrap("untrusted_job_post", f"Title: {job.get('title')}\n{clean}\nBudget: {job.get('budget')} ({job.get('budget_type')})\n"
                    f"Screening questions: {job.get('screening_questions')}")
        spec = await llm.call("analyst", system, user, JobSpec)
        if spec is not None:
            spec.job_id = job["id"]
            spec.screening_questions = job.get("screening_questions") or spec.screening_questions  # verbatim always
            spec.budget, spec.budget_type, spec.category = job.get("budget"), job.get("budget_type"), job.get("category")
            base = spec
    return {"spec": base.model_dump(), "_summary": f"{len(base.requirements)} requirements, {len(base.hidden_needs)} hidden needs"}
