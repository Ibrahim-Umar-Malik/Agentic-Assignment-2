"""Human-in-the-loop nodes (C5): dry-run preview, interrupt() for approval, edit re-check, exactly-once submit."""

from __future__ import annotations

import time

from langgraph.store.base import BaseStore
from langgraph.types import interrupt

from core.db import edits, engine, pipeline
from rag.verify import verify

from ..mcp_client import ToolGateway
from ..memory.promotion_rules import diff_edit, record_edit
from .common import node
from .verifier import to_evidence


@node("preview")
async def preview(state: dict) -> dict:
    gw = ToolGateway(state["user_id"])
    d, job = state["draft"], state["job"]
    v = d.get("version", 1)
    answers = [a["answer"] for a in d.get("screening_answers", [])]
    p1 = await gw.call("executor", "marketplace", "create_proposal_draft", {
        "job_id": job["id"], "cover_letter": d["cover_letter"], "bid_amount": state["price"]["amount"], "answers": answers,
        "idempotency_key": f"{state['thread_id']}:draft:v{v}:e{len(state.get('edits') or [])}", "dry_run": True})
    p2 = await gw.call("executor", "marketplace", "submit_proposal", {
        "draft_id": "pending", "job_id": job["id"], "idempotency_key": f"{state['thread_id']}:submit:preview", "dry_run": True})
    prev = {"would_send": p1.get("preview"), "connects_cost": p2.get("connects_cost"),
            "connects_balance_after": p2.get("connects_balance_after"), "marketplace": p1.get("marketplace")}
    return {"preview": prev, "status": "awaiting_approval", "_summary": f"Connects {prev['connects_cost']}, balance after {prev['connects_balance_after']}"}


def approval_payload(state: dict) -> dict:
    return {"kind": "proposal", "job": {k: state["job"].get(k) for k in ("id", "title", "budget", "budget_type", "category")},
            "draft": state["draft"], "evidence": state.get("evidence", []), "fit": state.get("fit"), "risk": state.get("risk"),
            "price": state.get("price"), "preview": state.get("preview"), "critiques": state.get("critiques", [])[-1:],
            "compliance": state.get("compliance"), "verification": state.get("verification"),
            "blocked": (state.get("compliance") or {}).get("status") == "block"}


@node("approval")
async def approval(state: dict, *, store: BaseStore | None = None) -> dict:
    decision = interrupt(approval_payload(state))  # graph pauses here; the web UI resumes it with Command(resume=...)
    action = (decision or {}).get("action")
    blocked = (state.get("compliance") or {}).get("status") == "block"
    if action == "approve" and not blocked:
        return {"approval": {"status": "approved", "by": decision.get("by"), "at": time.time()}, "status": "approved",
                "_summary": "approved by human"}
    if action == "reject" or (action == "approve" and blocked):
        reason = decision.get("reason") or ("compliance block" if blocked else "no reason given")
        return {"approval": {"status": "rejected", "reason": reason, "at": time.time()}, "status": "rejected",
                "status_reason": reason, "_summary": f"rejected: {reason}"}
    if action == "regenerate":
        return {"revision_request": {"paragraph": int(decision.get("paragraph", 0)), "instruction": decision.get("instruction", "")},
                "approval": {"status": "regenerating"}, "_summary": f"regenerate paragraph {decision.get('paragraph')}"}
    # edit: diff it, keep it for style memory (promotion rule decides), then re-check grounding + compliance
    before = state["draft"]["cover_letter"]
    after = decision.get("cover_letter", before)
    d = diff_edit(before, after)
    with engine().begin() as c:
        c.execute(edits.insert().values(user_id=state["user_id"], thread_id=state["thread_id"], before=before, after=after, diff=d))
    promoted = await record_edit(store, state["user_id"], state["thread_id"], before, after) if store is not None else []
    draft = dict(state["draft"], cover_letter=after, version=state["draft"].get("version", 1))
    if decision.get("screening_answers") is not None:
        draft["screening_answers"] = decision["screening_answers"]
    return {"draft": draft, "edits": [{"diff": d, "promoted": promoted, "at": time.time()}], "approval": {"status": "edited"},
            "_summary": f"edited ({d['len_before']}->{d['len_after']} words); promoted {promoted or 'nothing'}"}


@node("recheck")
async def recheck(state: dict) -> dict:
    """After a human edit: label claims again (nothing is removed; the Compliance Guard blocks unsupported ones)."""
    from ..mcp_client import ToolGateway as _GW

    gw = _GW(state["user_id"])
    pid = (state.get("meta") or {}).get("portfolio_id") or state.get("persona")
    skills = (await gw.call("verifier", "portfolio", "list_skills", {"portfolio_id": pid}))["skills"]
    vocab = [s["skill"] for s in skills if s["evidence_items"] > 0]
    items = list(state.get("evidence") or [])
    for iid in state["draft"].get("cited_items", [])[:5]:
        try:
            cs = await gw.call("verifier", "portfolio", "get_case_study", {"id": iid, "portfolio_id": pid})
            items.append({"id": cs["id"], "text": cs["text"], "skills": cs.get("skills", [])})
        except Exception:
            pass
    rep = verify(state["draft"]["cover_letter"], to_evidence(items), vocab)
    draft = dict(state["draft"], claims=[{"text": c["text"], "label": c["label"], "evidence_ids": c["evidence_ids"],
                                           "score": c["score"]} for c in rep["claims"]])
    return {"draft": draft, "_summary": f"{rep['unsupported_before']} unsupported claim(s) in the edited draft"}


@node("submit")
async def submit(state: dict) -> dict:
    """Runs only after approval. Idempotency keys derive from the thread + draft version, so a crash-and-resume
    re-run returns the first result instead of submitting (or spending Connects) twice."""
    gw = ToolGateway(state["user_id"])
    d, job = state["draft"], state["job"]
    v = f"v{d.get('version', 1)}e{len(state.get('edits') or [])}"
    created = await gw.call("executor", "marketplace", "create_proposal_draft", {
        "job_id": job["id"], "cover_letter": d["cover_letter"], "bid_amount": state["price"]["amount"],
        "answers": [a["answer"] for a in d.get("screening_answers", [])], "idempotency_key": f"{state['thread_id']}:draft:{v}"})
    draft_id = (created.get("result") or {}).get("id")
    sub = await gw.call("executor", "marketplace", "submit_proposal", {
        "draft_id": draft_id, "job_id": job["id"], "idempotency_key": f"{state['thread_id']}:submit:{v}"})
    res = sub.get("result") or {}
    with engine().begin() as c:
        c.execute(pipeline.delete().where(pipeline.c.user_id == state["user_id"], pipeline.c.job_id == job["id"]))
        c.execute(pipeline.insert().values(user_id=state["user_id"], job_id=job["id"], stage="submitted", title=job.get("title"),
                                           proposal_id=res.get("id"), bid=state["price"]["amount"], category=job.get("category"),
                                           connects=sub.get("connects_cost")))
    return {"submission": {"status": sub.get("status"), "proposal_id": res.get("id"), "marketplace_status": res.get("status"),
                           "connects_spent": sub.get("connects_cost"), "duplicate": sub.get("status") == "duplicate"},
            "status": "submitted", "_summary": f"submitted ({sub.get('status')}) proposal {res.get('id')}"}


@node("needs_attention")
async def needs_attention(state: dict) -> dict:
    from .common import over_budget

    return {"status": "needs_attention", "status_reason": over_budget(state) or "budget exceeded"}
