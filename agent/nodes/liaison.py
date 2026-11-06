"""Client Liaison: classify the client's latest message, draft a reply or interview slots, keep the pipeline current."""

from __future__ import annotations

import re
import time
from datetime import datetime

from langgraph.types import interrupt

from core import llm
from core.db import engine, pipeline

from ..handoffs import MessageIntent, ReplyDraft
from ..mcp_client import ToolGateway
from .common import injection_spans, load_prompt, node, risk_patterns, sanitize_untrusted, wrap


def classify(text: str) -> MessageIntent:
    for p in risk_patterns()["scam"]:
        if re.search(p["pattern"], text) and p["kind"] in ("off_platform", "scam", "contact_harvest", "advance_fee"):
            return MessageIntent(intent="scam_signal", confidence=0.9, summary="asks to move off-platform or pay outside")
    m = re.search(r"\$\s?(\d[\d,]*)", text)
    if re.search(r"(?i)\b(rate|price|budget|cheaper|discount|lower|could you do it for)\b", text):
        return MessageIntent(intent="negotiation", confidence=0.8, summary="price negotiation",
                             requested_rate=float(m.group(1).replace(",", "")) if m else None)
    if re.search(r"(?i)\b(call|interview|meet|chat|schedule|available)\b", text):
        return MessageIntent(intent="interview_request", confidence=0.85, summary="asks for a call")
    if "?" in text:
        return MessageIntent(intent="question", confidence=0.7, summary="asks a question")
    return MessageIntent(intent="other", confidence=0.5, summary="acknowledgement")


@node("intent")
async def intent(state: dict) -> dict:
    msg = state["new_message"]["body"]
    it = classify(msg)
    if not llm.is_offline("intent") and it.intent != "scam_signal":
        _, system = load_prompt("intent")
        clean, _ = sanitize_untrusted(msg)
        out = await llm.call("intent", system, wrap("untrusted_client_message", clean), MessageIntent)
        if out is not None:
            it = out if out.intent != "other" or it.intent == "other" else it
    if injection_spans(msg):
        it.summary += " (message contains instructions aimed at AI tools: ignored)"
    return {"intent": it.model_dump(), "_summary": f"{it.intent} ({it.confidence:.2f})"}


def _fmt(slot: dict, tz: str) -> str:
    s = datetime.fromisoformat(slot["start"])
    return s.strftime("%a %d %b, %H:%M") + f" ({tz})"


@node("liaison")
async def draft_reply(state: dict) -> dict:
    gw = ToolGateway(state["user_id"])
    it = state["intent"]
    floor = float((state.get("meta") or {}).get("hourly_floor") or 0)
    bid = float((state.get("proposal") or {}).get("bid_amount") or 0)
    slots, tz = [], ""
    walk = False
    kind = it["intent"]
    if kind == "interview_request":
        res = await gw.call("liaison", "workspace", "free_slots", {"days": 5, "duration_min": 30})
        slots, tz = res["slots"][:3], res["timezone"]
        body = ("Thanks, happy to talk. I'm free at " + "; ".join(_fmt(s, tz) for s in slots) +
                ". Let me know which suits you and I'll keep it reserved.")
    elif kind == "negotiation":
        ask = it.get("requested_rate")
        job = state.get("job") or {}
        minimum = floor if job.get("budget_type") == "hourly" else max(floor * 8, bid * 0.85)
        if ask and ask < minimum:
            walk = True
            body = (f"I appreciate the flexibility. I can't go below ${minimum:,.0f} for the full scope, but at ${ask:,.0f} I could deliver "
                    "a smaller first milestone so you can judge the work before committing to the rest. Would that help?")
        else:
            body = (f"That works for me at ${ask:,.0f} if we keep the scope as described in the post. Shall I outline the milestones?"
                    if ask else "I'm open to adjusting scope to fit your budget. Which parts matter most to you?")
    elif kind == "scam_signal":
        body = ("Thanks for getting back to me. I keep all communication and payments on the platform, as its terms require, "
                "so let's continue here. Happy to answer any questions about the project.")
    elif kind == "question":
        ev = (state.get("evidence") or [{}])[0]
        how = ev.get("snippet", "").split("## What I did")[-1].split("##")[0].strip() if ev else ""
        body = ("Good question. " + (f"In my {ev.get('title', 'previous project')} I {how[:1].lower() + how[1:]} " if how else "") +
                "For your project I would start with a short discovery call, then deliver a first testable milestone within a week.")
    else:
        body = "Thanks for the update. Let me know if there's anything else you need from me."
    reply = ReplyDraft(body=body, proposed_slots=slots, walk_away=walk)
    if not llm.is_offline("liaison") and kind != "scam_signal":
        _, system = load_prompt("liaison")
        clean, _ = sanitize_untrusted(state["new_message"]["body"])
        out = await llm.call("liaison", system, wrap("untrusted_client_message", clean) +
                             f"\nIntent: {kind}\nFloor rate: {floor}\nSlots (offer exactly these): "
                             f"{[_fmt(s, tz) for s in slots]}\nEvidence: {[e.get('snippet', '')[:300] for e in (state.get('evidence') or [])[:3]]}"
                             f"\nBaseline draft: {body}", ReplyDraft)
        if out is not None:
            out.proposed_slots, out.walk_away = slots, walk
            reply = out
    return {"reply": reply.model_dump(), "slots": slots, "_summary": f"{kind} reply, {len(body.split())} words"}


@node("preview_message")
async def preview_message(state: dict) -> dict:
    gw = ToolGateway(state["user_id"])
    p = await gw.call("executor", "marketplace", "send_message", {
        "thread_id": state["thread_id"], "body": state["reply"]["body"],
        "idempotency_key": f"{state['thread_id']}:{state['new_message']['id']}:preview", "dry_run": True})
    return {"preview": {"would_send": p.get("preview"), "marketplace": p.get("marketplace")}, "status": "awaiting_approval"}


@node("approval_message")
async def approval_message(state: dict) -> dict:
    decision = interrupt({"kind": "message", "thread_id": state["thread_id"], "client_message": state["new_message"],
                          "intent": state.get("intent"), "reply": state["reply"], "slots": state.get("slots", []),
                          "compliance": state.get("compliance"), "preview": state.get("preview"),
                          "blocked": (state.get("compliance") or {}).get("status") == "block"})
    action = (decision or {}).get("action")
    blocked = (state.get("compliance") or {}).get("status") == "block"
    if action == "approve" and not blocked:
        return {"approval": {"status": "approved", "slot": decision.get("slot"), "at": time.time()}, "status": "approved"}
    if action == "edit":
        return {"reply": dict(state["reply"], body=decision.get("body", state["reply"]["body"]),
                              version=state["reply"].get("version", 1) + 1),
                "edits": [{"before": state["reply"]["body"], "after": decision.get("body")}], "approval": {"status": "edited"}}
    return {"approval": {"status": "rejected", "reason": decision.get("reason", "")}, "status": "rejected",
            "status_reason": decision.get("reason", "")}


@node("send")
async def send(state: dict) -> dict:
    gw = ToolGateway(state["user_id"])
    v = state["reply"].get("version", 1)
    sent = await gw.call("executor", "marketplace", "send_message", {
        "thread_id": state["thread_id"], "body": state["reply"]["body"],
        "idempotency_key": f"{state['thread_id']}:{state['new_message']['id']}:v{v}"})
    hold = {}
    slots = state.get("slots") or []
    if slots:
        s = slots[int((state.get("approval") or {}).get("slot") or 0) % len(slots)]
        hold = await gw.call("liaison", "workspace", "create_interview_hold",
                             {"start": s["start"], "end": s["end"], "title": f"Interview: {(state.get('job') or {}).get('title', '')[:80]}"})
    stage = {"interview_request": "interview"}.get(state["intent"]["intent"], "replied")
    job_id = (state.get("job") or {}).get("id")
    if job_id:
        with engine().begin() as c:
            c.execute(pipeline.update().where(pipeline.c.user_id == state["user_id"], pipeline.c.job_id == job_id)
                      .values(stage=stage, thread_id=state["thread_id"], updated_at=time.time()))
    return {"sent": sent, "hold": hold, "status": "sent", "_summary": f"sent ({sent.get('status')})"}
