"""Fit Matcher: map every requirement to portfolio evidence (through the Portfolio MCP server) and score fit."""

from __future__ import annotations

from core import config, llm
from rag.index.skills import MARKET_SKILLS, broad_children, expand, find_skills
from rag.types import tokenize

from ..handoffs import EvidenceRef, FitReport, RequirementMatch
from ..mcp_client import ToolGateway
from .common import node


def coverage(requirement: str, items: list[dict]) -> str:
    terms = set(tokenize(expand(requirement)))
    children = [c.lower() for c in broad_children(requirement)]
    best = 0.0
    for it in items[:3]:
        hay = (it.get("snippet", "") + " " + " ".join(it.get("skills", []))).lower()
        if requirement.lower() in hay:
            return "full"
        # An umbrella tag ("Machine Learning") is evidenced by a specific skill under it ("LightGBM").
        if children and sum(1 for c in children if c in hay) >= 1:
            return "full"
        best = max(best, len(terms & set(tokenize(hay))) / max(1, len(terms)))
    return "full" if best >= 0.6 else "partial" if best >= 0.3 else "none"


@node("matcher")
async def matcher(state: dict) -> dict:
    gw = ToolGateway(state["user_id"])
    job = state["job"]
    pid = state.get("meta", {}).get("portfolio_id") or state.get("persona")
    excluded = state.get("meta", {}).get("deleted_items", [])
    skills = (await gw.call("matcher", "portfolio", "list_skills", {"portfolio_id": pid}))["skills"]
    vocab = [s["skill"] for s in skills]
    text = f"{job.get('title', '')}. {job.get('description', '')}"
    title_skills = find_skills(job.get("title", ""), MARKET_SKILLS + vocab)
    reqs = list(dict.fromkeys(title_skills + (job.get("skills") or []) + find_skills(text, vocab)))[:8]
    if not reqs:
        reqs = [s for s in text.split(". ") if len(s.split()) > 4][:3] or [job.get("title", "")]
    matrix: list[RequirementMatch] = []
    evidence: dict[str, dict] = {}
    for r in reqs:
        res = await gw.call("matcher", "portfolio", "search_evidence",
                            {"requirement": r, "k": 4, "portfolio_id": pid, "filters": {"exclude_ids": excluded}})
        items = res.get("items", [])
        cov = coverage(r, items) if items else "none"
        refs = [EvidenceRef(item_id=i["id"], project=i.get("project"), type=i.get("type"), title=i.get("title"),
                            snippet=i.get("snippet", "")[:300], score=i.get("score", 0), outcome=i.get("outcome"))
                for i in items[:3]] if cov != "none" else []
        matrix.append(RequirementMatch(requirement=r, coverage=cov, evidence=refs))
        for i in items[:3] if cov != "none" else []:
            evidence.setdefault(i["id"], {**i, "requirement": r})
    known = {v.lower() for v in vocab}
    generic = {g.lower() for g in config.get("decision.generic_skills", [])}
    title = job.get("title", "").lower()

    def weight(r: str) -> float:  # the skill in the title is what the client is hiring for; generic skills count less
        return 2.0 if r.lower() in title else 0.5 if r.lower() in generic else 1.0

    w = {"full": 1.0, "partial": 0.5, "none": 0.0}
    tot = sum(weight(m.requirement) for m in matrix) or 1.0
    cov_score = sum(weight(m.requirement) * w[m.coverage] for m in matrix) / tot
    in_domain = sum(weight(r) for r in reqs if r.lower() in known) / (sum(weight(r) for r in reqs) or 1.0)
    fit = 0.75 * cov_score + 0.25 * in_domain
    if any(m.coverage == "none" and m.requirement.lower() in title for m in matrix):
        fit *= config.get("decision.title_skill_missing_penalty", 0.6)
    fit = round(fit, 3)
    projects: dict[str, int] = {}
    for m in matrix:
        for e in m.evidence:
            if e.project:
                projects[e.project] = projects.get(e.project, 0) + 1
    report = FitReport(
        fit_score=fit, matrix=matrix,
        reasons=[f"{sum(m.coverage == 'full' for m in matrix)}/{len(matrix)} requirements fully evidenced",
                 f"{in_domain:.0%} of requirements are skills in the portfolio"],
        unsupported_requirements=[m.requirement for m in matrix if m.coverage == "none"],
        top_projects=sorted(projects, key=lambda p: -projects[p])[:3])
    _ = llm  # matcher grading is deterministic; the LLM path is used only for the writer
    return {"fit": report.model_dump(), "evidence": list(evidence.values()),
            "_summary": f"fit {fit:.2f}; unsupported: {', '.join(report.unsupported_requirements) or 'none'}"}
