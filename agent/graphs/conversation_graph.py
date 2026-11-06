"""Conversation graph (one thread per client conversation): classify intent -> draft reply / interview slots
-> compliance -> dry-run preview -> approval (interrupt) -> send (+ tentative calendar hold)."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from ..mcp_client import ToolGateway
from ..nodes.common import node, over_budget
from ..nodes.compliance import compliance
from ..nodes.liaison import approval_message, draft_reply, intent, preview_message, send
from ..state import ConversationState

RETRY = RetryPolicy(max_attempts=3, initial_interval=1.0, retry_on=lambda e: not isinstance(e, (PermissionError, ValueError)))


@node("context")
async def context(state: dict) -> dict:
    """Evidence for answering questions: search the portfolio with the client's message (Portfolio read)."""
    if state.get("evidence"):
        return {}
    res = await ToolGateway(state["user_id"]).call("liaison", "portfolio", "search_evidence", {
        "requirement": state["new_message"]["body"][:300], "k": 3, "portfolio_id": state.get("persona"),
        "filters": {"type": "case_study"}})
    return {"evidence": res.get("items", [])}


async def compliance_reply(state: dict) -> dict:
    return await compliance(state, "reply")


def after_approval(state: dict) -> str:
    if over_budget(state):
        return END
    return {"approved": "send", "edited": "compliance", "rejected": END}.get((state.get("approval") or {}).get("status"), END)


def build_conversation_graph() -> StateGraph:
    g = StateGraph(ConversationState)
    g.add_node("context", context)
    g.add_node("intent", intent, retry_policy=RETRY, timeout=60.0)
    g.add_node("liaison", draft_reply, retry_policy=RETRY, timeout=90.0)
    g.add_node("compliance", compliance_reply)
    g.add_node("preview", preview_message, retry_policy=RETRY)
    g.add_node("approval", approval_message)
    g.add_node("send", send, retry_policy=RETRY)
    g.add_edge(START, "context")
    g.add_edge("context", "intent")
    g.add_edge("intent", "liaison")
    g.add_edge("liaison", "compliance")
    g.add_edge("compliance", "preview")
    g.add_edge("preview", "approval")
    g.add_conditional_edges("approval", after_approval, ["send", "compliance", END])
    g.add_edge("send", END)
    return g
