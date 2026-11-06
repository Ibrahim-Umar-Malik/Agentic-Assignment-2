"""Bid graph (one thread per job), a hand-written StateGraph (R3, C1).

scout -> [analyst | risk | matcher] in parallel (Send) -> decide -> pricing -> writer -> verifier -> critic
      -> (writer again, at most critic.max_revisions times) -> compliance -> preview (dry_run) -> approval (interrupt)
      -> submit                       edit -> recheck -> compliance -> preview -> approval
                                      regenerate paragraph -> writer ...      reject -> END
Every router checks the step/token budget first and diverts to needs_attention.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send

from core import config

from ..nodes.analyst import analyst
from ..nodes.approval import approval, needs_attention, preview, recheck, submit
from ..nodes.common import over_budget
from ..nodes.compliance import compliance
from ..nodes.critic import critic
from ..nodes.decision import decision
from ..nodes.matcher import matcher
from ..nodes.pricing import pricing
from ..nodes.risk import risk
from ..nodes.scout import intake
from ..nodes.verifier import verifier
from ..nodes.writer import writer
from ..state import BidState

RETRY = RetryPolicy(max_attempts=3, initial_interval=1.0, backoff_factor=2.0,
                    retry_on=lambda e: not isinstance(e, (PermissionError, ValueError)))
LLM_TIMEOUT = 120.0


def fan_out(state: BidState):
    if over_budget(state):
        return "needs_attention"
    if (state.get("meta") or {}).get("duplicate_of"):
        return "decide"
    return [Send("analyst", state), Send("risk", state), Send("matcher", state)]


def after_decide(state: BidState) -> str:
    if over_budget(state):
        return "needs_attention"
    return "pricing" if (state.get("decision") or {}).get("action") == "bid" else END


def after_pricing(state: BidState) -> str:
    return END if state.get("status") == "skipped" else "writer"


def after_critic(state: BidState) -> str:
    if over_budget(state):
        return "needs_attention"
    last = (state.get("critiques") or [{}])[-1]
    if last.get("approve") or int(state.get("revisions") or 0) >= config.get("critic.max_revisions", 2):
        return "compliance"
    return "writer"


def after_approval(state: BidState) -> str:
    if over_budget(state):
        return "needs_attention"
    st = (state.get("approval") or {}).get("status")
    return {"approved": "submit", "rejected": END, "regenerating": "writer", "edited": "recheck"}.get(st, END)


def build_bid_graph() -> StateGraph:
    g = StateGraph(BidState)
    g.add_node("scout", intake)
    g.add_node("analyst", analyst, retry_policy=RETRY, timeout=LLM_TIMEOUT)
    g.add_node("risk", risk, retry_policy=RETRY, timeout=LLM_TIMEOUT)
    g.add_node("matcher", matcher, retry_policy=RETRY, timeout=LLM_TIMEOUT)
    g.add_node("decide", decision, defer=True)  # join: waits for all three parallel branches
    g.add_node("pricing", pricing, retry_policy=RETRY, timeout=LLM_TIMEOUT)
    g.add_node("writer", writer, retry_policy=RETRY, timeout=LLM_TIMEOUT)
    g.add_node("verifier", verifier, retry_policy=RETRY, timeout=LLM_TIMEOUT)
    g.add_node("critic", critic, retry_policy=RETRY, timeout=LLM_TIMEOUT)
    g.add_node("compliance", compliance, retry_policy=RETRY, timeout=LLM_TIMEOUT)
    g.add_node("preview", preview, retry_policy=RETRY)
    g.add_node("approval", approval)
    g.add_node("recheck", recheck, retry_policy=RETRY)
    g.add_node("submit", submit, retry_policy=RETRY)
    g.add_node("needs_attention", needs_attention)

    g.add_edge(START, "scout")
    g.add_conditional_edges("scout", fan_out, ["analyst", "risk", "matcher", "decide", "needs_attention"])
    for n in ("analyst", "risk", "matcher"):
        g.add_edge(n, "decide")
    g.add_conditional_edges("decide", after_decide, ["pricing", "needs_attention", END])
    g.add_conditional_edges("pricing", after_pricing, ["writer", END])
    g.add_edge("writer", "verifier")
    g.add_edge("verifier", "critic")
    g.add_conditional_edges("critic", after_critic, ["writer", "compliance", "needs_attention"])
    g.add_edge("compliance", "preview")
    g.add_edge("preview", "approval")
    g.add_conditional_edges("approval", after_approval, ["submit", "writer", "recheck", "needs_attention", END])
    g.add_edge("recheck", "compliance")
    g.add_edge("submit", END)
    g.add_edge("needs_attention", END)
    return g
