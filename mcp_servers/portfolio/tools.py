"""Portfolio tools: search_evidence, get_case_study, list_skills (all read-only)."""

from __future__ import annotations

from collections import Counter
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import backend

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
ItemType = Literal["case_study", "repo_readme", "repo_code", "review", "proposal", "cv"]


class EvidenceFilters(BaseModel):
    type: ItemType | None = None
    project: str | None = None
    outcome: Literal["won", "replied", "ignored"] | None = None
    skill: str | None = None
    exclude_ids: list[str] = Field(default_factory=list, description="Evidence item ids to leave out (e.g. deleted).")


class EvidenceItem(BaseModel):
    id: str = Field(description="Item id; load it in full via portfolio://case/{id} or portfolio://proposal/{id}")
    type: str
    source: str | None
    date: str | None
    outcome: str | None = None
    project: str | None = None
    title: str | None = None
    skills: list[str] = []
    snippet: str
    score: float


class EvidenceResult(BaseModel):
    requirement: str
    items: list[EvidenceItem]
    note: str | None = None


class CaseStudy(BaseModel):
    id: str
    title: str | None
    project: str | None
    date: str | None
    client_industry: str | None = None
    skills: list[str] = []
    text: str
    related: list[str] = Field(default_factory=list, description="Other items about the same project (README, code, reviews, proposals)")


class SkillCount(BaseModel):
    skill: str
    evidence_items: int


class SkillList(BaseModel):
    skills: list[SkillCount]


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=READ, description=(
        "Find portfolio evidence for ONE requirement (e.g. 'Celery background jobs' or 'RAG for legal documents'). "
        "Returns ranked items with type, source, date and, for past proposals, their outcome. Call once per requirement."))
    def search_evidence(requirement: Annotated[str, Field(min_length=1, max_length=300)],
                        k: Annotated[int, Field(ge=1, le=20)] = 5,
                        filters: EvidenceFilters | None = None,
                        portfolio_id: Annotated[str | None, Field(max_length=120, description="Leave empty for your own portfolio")] = None,
                        ) -> EvidenceResult:
        idx = backend.get(portfolio_id)
        f = filters or EvidenceFilters()
        ev = idx.search(requirement, k=max(k * 3, 10), opts=backend.DEFAULT_OPTIONS)
        out: list[EvidenceItem] = []
        for e in ev:
            m = e.chunk.meta
            iid = m.get("item_id") or e.chunk.doc_id
            if iid in f.exclude_ids or (f.type and m.get("type") != f.type) or (f.project and m.get("project") != f.project):
                continue
            if f.outcome and m.get("outcome") != f.outcome:
                continue
            if f.skill and f.skill.lower() not in (e.chunk.text + " ".join(m.get("skills", []))).lower():
                continue
            out.append(EvidenceItem(id=iid, type=m.get("type", ""), source=m.get("source"), date=m.get("date"), outcome=m.get("outcome"),
                                    project=m.get("project"), title=m.get("title"), skills=m.get("skills", []),
                                    snippet=e.chunk.text[:500], score=round(e.score, 4)))
            if len(out) >= k:
                break
        return EvidenceResult(requirement=requirement, items=out,
                              note=None if out else "No supporting evidence found. Do not claim this requirement.")

    @mcp.tool(annotations=READ, description="Load a full case study (or any portfolio item) by id, with related items.")
    def get_case_study(id: Annotated[str, Field(min_length=1, max_length=200)],
                       portfolio_id: Annotated[str | None, Field(max_length=120)] = None) -> CaseStudy:
        idx = backend.get(portfolio_id)
        doc = idx.by_item.get(id) or next((d for d in idx.docs if d.id == id or d.meta.get("project") == id), None)
        if doc is None:
            raise ValueError(f"no portfolio item {id}")
        proj = doc.meta.get("project")
        related = sorted({d.meta.get("item_id") or d.id for d in idx.docs if proj and d.meta.get("project") == proj} - {id})
        return CaseStudy(id=doc.meta.get("item_id") or doc.id, title=doc.meta.get("title"), project=proj, date=doc.meta.get("date"),
                         client_industry=doc.meta.get("client_industry"), skills=doc.meta.get("skills", []), text=doc.text,
                         related=related)

    @mcp.tool(annotations=READ, description="All skills in the portfolio with how many evidence items support each.")
    def list_skills(portfolio_id: Annotated[str | None, Field(max_length=120)] = None) -> SkillList:
        idx = backend.get(portfolio_id)
        cnt: Counter = Counter()
        for d in idx.docs:
            for s in set(d.meta.get("skills", [])) if d.meta.get("type") != "cv" else []:
                cnt[s] += 1
        for s in idx.vocab:
            cnt.setdefault(s, 0)
        return SkillList(skills=[SkillCount(skill=s, evidence_items=n) for s, n in sorted(cnt.items(), key=lambda x: (-x[1], x[0]))])
