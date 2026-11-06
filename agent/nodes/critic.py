"""Critic: grounding, personalisation, length; sends the draft back at most critic.max_revisions times."""

from __future__ import annotations

import re

from core import config, llm

from ..handoffs import Critique, CritiqueIssue
from .common import load_prompt, node


def heuristic_critique(state: dict) -> Critique:
    c = config.get("critic", {})
    d = state["draft"]
    text = d["cover_letter"]
    issues: list[CritiqueIssue] = []
    words = len(text.split())
    if words > c.get("max_words", 260):
        issues.append(CritiqueIssue(kind="length", detail=f"{words} words; keep it under {c.get('max_words')}", paragraph=len(text.split('\n\n')) - 1))
    if words < 60:
        issues.append(CritiqueIssue(kind="length", detail=f"only {words} words; add one concrete proof point"))
    first = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0].lower() if text.strip() else ""
    if any(b in first for b in c.get("banned_openings", [])):
        issues.append(CritiqueIssue(kind="generic_opening", detail="generic first sentence", paragraph=0))
    partial = [cl for cl in d.get("claims", []) if cl["label"] != "supported"]
    if partial:
        issues.append(CritiqueIssue(kind="grounding", detail=f"{len(partial)} claim(s) only partly supported: '{partial[0]['text'][:80]}'"))
    reqs = [m["requirement"] for m in (state.get("fit") or {}).get("matrix", []) if m["coverage"] != "none"]
    mentioned = sum(1 for r in reqs if r.lower() in text.lower())
    if reqs and mentioned / len(reqs) < 0.5:
        issues.append(CritiqueIssue(kind="personalisation", detail=f"mentions {mentioned}/{len(reqs)} of the client's requirements"))
    qs = state["job"].get("screening_questions") or []
    if len([a for a in d.get("screening_answers", []) if a["answer"].strip()]) < len(qs):
        issues.append(CritiqueIssue(kind="screening", detail="not every screening question is answered"))
    penalty = {"length": 0.15, "generic_opening": 0.25, "grounding": 0.2, "personalisation": 0.2, "screening": 0.25}
    score = max(0.0, 1.0 - sum(penalty.get(i.kind, 0.1) for i in issues))
    approve = score >= c.get("min_score", 0.7) and not any(i.kind == "grounding" for i in issues)
    return Critique(score=round(score, 2), approve=approve, issues=issues,
                    revision_instructions="; ".join(f"{i.kind}: {i.detail}" for i in issues))


@node("critic")
async def critic(state: dict) -> dict:
    crit = heuristic_critique(state)
    if not llm.is_offline("critic"):
        _, system = load_prompt("critic", min_score=config.get("critic.min_score", 0.7))
        out = await llm.call("critic", system, f"JOB: {state['job'].get('title')}\nREQUIREMENTS: {state.get('spec', {}).get('requirements')}\n"
                             f"HIDDEN NEEDS: {state.get('spec', {}).get('hidden_needs')}\nDRAFT:\n{state['draft']['cover_letter']}\n"
                             f"CLAIM LABELS: {state['draft'].get('claims')}", Critique)
        if out is not None:  # both must approve; issues are merged
            crit = Critique(score=round(min(crit.score, out.score), 2), approve=crit.approve and out.approve,
                            issues=crit.issues + out.issues, revision_instructions="; ".join(
                                x for x in [crit.revision_instructions, out.revision_instructions] if x))
    return {"critiques": [crit.model_dump() | {"version": state["draft"].get("version")}],
            "_summary": f"score {crit.score}, {'approve' if crit.approve else 'revise'}"}
