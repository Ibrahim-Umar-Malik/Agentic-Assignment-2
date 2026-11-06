"""Proposal Writer: cover letter + screening answers with evidence citations (Portfolio read)."""

from __future__ import annotations

import re

from langgraph.store.base import BaseStore

from core import llm

from ..handoffs import ProposalDraft, ScreeningAnswer
from ..memory.store import outcome_insights, style_rules
from .common import load_prompt, node, sanitize_untrusted, wrap


def _section(text: str, name: str) -> str:
    m = re.search(rf"##\s*{name}\s*\n(.+?)(\n##|\Z)", text, re.S | re.I)
    return m.group(1).strip() if m else ""


def _lc(s: str) -> str:
    if not s or (len(s) > 1 and (s[1].isupper() or s[1].isdigit())):
        return s  # keep acronyms such as LoRA, LLM
    return s[:1].lower() + s[1:]


def _best(evidence: list[dict], requirement: str | None = None, prefer=("case_study", "repo_readme", "review"),
          project: str | None = None) -> dict | None:
    """Best citable item: a case study (or README / review) of the project that proves the requirement.
    Past proposals and the CV are evidence for retrieval but are not cited as proof in a letter."""
    pool = [e for e in evidence if (requirement is None or e.get("requirement") == requirement)] or evidence
    if project:
        pool = [e for e in evidence if e.get("project") == project] or pool
    for t in prefer:
        for e in pool:
            if e.get("type") == t:
                return e
    return None


def heuristic_draft(state: dict, styles: list[dict], insights: list[dict], version: int) -> ProposalDraft:
    job, fit = state["job"], state.get("fit") or {}
    spec = state.get("spec") or {}
    evidence = state.get("evidence") or []
    matrix = fit.get("matrix", [])
    covered = [m for m in matrix if m["coverage"] != "none"]
    missing = [m["requirement"] for m in matrix if m["coverage"] == "none"]
    cited: list[str] = []
    paras: list[str] = []
    top = (fit.get("top_projects") or [None])[0]
    lead = _best(evidence, project=top) if top else _best(evidence, covered[0]["requirement"] if covered else None)
    question_first = any(i.get("opening") == "question" for i in insights)
    req0 = covered[0]["requirement"] if covered else (spec.get("requirements") or [{"text": "this"}])[0]["text"]
    question = f"Is the {req0} part already started, or would this be built from scratch?"
    if lead:
        result = _section(lead.get("snippet", ""), "Result") or lead.get("snippet", "").split("\n")[-1][:200]
        title = lead.get("title") or lead.get("project")
        opening = f"{result.rstrip('.')}: that was the outcome of my {_lc(title)} project, which is close to what you describe."
        if question_first:
            opening = question + " " + opening
        paras.append(opening)
        cited.append(lead["id"])
    proof = []
    for m in covered[:3]:
        e = _best(evidence, m["requirement"])
        if not e or e["id"] in cited:
            continue
        approach = _section(e.get("snippet", ""), "What I did") or ""
        if approach:
            proof.append(f"For {m['requirement']}: in the {_lc(e.get('title') or e.get('project'))} project I {_lc(approach).rstrip('.')}.")
        else:
            continue
        cited.append(e["id"])
    if proof:
        paras.append(" ".join(dict.fromkeys(proof)))
    if missing:
        paras.append(f"I have not used {', '.join(missing[:2])} in client work, so I would start with a short spike and confirm the approach with you before building on it.")
    needs = spec.get("hidden_needs") or []
    plan = "Plan: a short discovery call, a first working milestone you can test, then documentation and a handover call."
    if needs:
        plan = f"Since you need {needs[0]}, my plan is a short discovery call, a first working milestone you can test, then documentation and a handover call."
    paras.append(plan)
    if not question_first:
        paras.append(question)
    letter = "\n\n".join(paras)
    for s in styles:
        k = s.get("key", "")
        if k.startswith("never_say:"):
            letter = re.sub(rf"(?i)\b{re.escape(k.split(':', 1)[1])}\b ?", "", letter)
    answers = []
    for q in job.get("screening_questions") or []:
        ql = q.lower()
        e = _best(evidence) or {}
        if "similar project" in ql or "relevant work" in ql or "link" in ql:
            a = (f"My {_lc(e.get('title') or 'most relevant')} project: {(_section(e.get('snippet', ''), 'Result') or '').strip()} "
                 "The case study and code are in my marketplace portfolio and I can walk you through them on a call.")
        elif "approach" in ql:
            req = next((m["requirement"] for m in covered if m["requirement"].lower() in ql), req0)
            e2 = _best(evidence, req) or e
            a = (f"I would start from what worked in my {_lc(e2.get('title') or 'previous')} project: "
                 f"{_lc(_section(e2.get('snippet', ''), 'What I did') or 'a small working prototype first')} "
                 "Then I would agree milestones with you so each one is testable.")
        elif "availability" in ql:
            a = f"I can commit about {(state.get('meta') or {}).get('hours_per_week', 20)} hours per week and reply within one working day."
        elif "need from us" in ql or "start" in ql:
            a = "Access to the current code or data, one sample of the expected output, and a 30-minute kickoff to agree the first milestone."
        else:
            a = "Happy to answer this in detail on a short call; the summary is in my cover letter above."
        answers.append(ScreeningAnswer(question=q, answer=a.replace("  ", " ")))
    return ProposalDraft(cover_letter=letter, screening_answers=answers, version=version,
                         strategy="question_first" if question_first else "evidence_first", cited_items=list(dict.fromkeys(cited)))


def apply_paragraph_regen(old: str, new: str, idx: int) -> str:
    po, pn = old.split("\n\n"), new.split("\n\n")
    if 0 <= idx < len(po):
        po[idx] = pn[idx] if idx < len(pn) and pn[idx] != po[idx] else (pn[(idx + 1) % len(pn)] if pn else po[idx])
    return "\n\n".join(po)


@node("writer")
async def writer(state: dict, *, store: BaseStore | None = None) -> dict:
    uid = state["user_id"]
    styles = await style_rules(store, uid)
    insights = await outcome_insights(store, uid, (state.get("job") or {}).get("category"))
    version = int((state.get("draft") or {}).get("version", 0)) + 1
    critique = (state.get("critiques") or [{}])[-1] if state.get("critiques") else {}
    regen = state.get("revision_request") or {}
    draft = heuristic_draft(state, styles, insights, version)
    if not llm.is_offline("writer"):
        instructions = ""
        if critique and not critique.get("approve", True):
            instructions = "Revise the previous draft. Critic says: " + critique.get("revision_instructions", "")
        if regen:
            instructions = (f"Rewrite ONLY paragraph {regen.get('paragraph', 0) + 1} of the previous draft. "
                            f"User instruction: {regen.get('instruction', 'make it more specific')}")
        _, system = load_prompt("writer", style_rules="\n".join(f"- {s['rule']}" for s in styles) or "- (none yet)",
                                outcome_insights="\n".join(f"- {i['rule']}" for i in insights) or "- (not enough outcomes yet)",
                                revision_instructions=instructions)
        clean, _ = sanitize_untrusted(state["job"].get("description", ""))
        ev = "\n".join(f"[{e['id']}] ({e.get('type')}, {e.get('title')}, outcome={e.get('outcome')}) {e.get('snippet', '')[:400]}"
                       for e in (state.get("evidence") or [])[:10])
        user = (wrap("untrusted_job_post", f"{state['job'].get('title')}\n{clean}") +
                f"\n\nJobSpec: {state.get('spec')}\nUnsupported requirements (do not claim): "
                f"{(state.get('fit') or {}).get('unsupported_requirements')}\nPrice: {state.get('price', {}).get('amount')}\n"
                f"Screening questions: {state['job'].get('screening_questions')}\n\nEVIDENCE:\n{ev}\n\n"
                f"Previous draft:\n{(state.get('draft') or {}).get('cover_letter', '(none)')}")
        out = await llm.call("writer", system, user, ProposalDraft)
        if out is not None:
            out.version = version
            draft = out
    if regen and state.get("draft"):
        draft.cover_letter = apply_paragraph_regen(state["draft"]["cover_letter"], draft.cover_letter, int(regen.get("paragraph", 0)))
    return {"draft": draft.model_dump(), "revision_request": {}, "revisions": int(state.get("revisions") or 0) + (1 if critique else 0),
            "_summary": f"v{version}, {len(draft.cover_letter.split())} words, cites {len(draft.cited_items)} items"}
