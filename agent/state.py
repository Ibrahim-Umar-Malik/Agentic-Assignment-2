"""Typed graph state with reducers wherever parallel branches write (C2).

Three things are kept apart (see docs/ARCHITECTURE.md):
  * State (this module): what one job or conversation needs right now. Hand-offs are Pydantic objects
    serialised to dicts so the Postgres checkpointer can store them.
  * Execution trace: every tool name, argument, result and model call, written by core.tracing to trace_spans
    (and the audit log for marketplace tools). Never stored in state; state only keeps the trace id.
  * Long-term memory: only promoted knowledge, written to the LangGraph store by agent/memory/promotion_rules.py.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_dicts(a: dict | None, b: dict | None) -> dict:
    return {**(a or {}), **(b or {})}


class BidState(TypedDict, total=False):
    # identity
    user_id: str
    persona: str
    thread_id: str
    trace_id: str
    autonomy: str
    # inputs
    job: dict[str, Any]
    client: dict[str, Any]
    # analyses: written by the three parallel branches, each to its own key
    spec: dict[str, Any]          # JobSpec
    risk: dict[str, Any]          # RiskReport
    fit: dict[str, Any]           # FitReport
    evidence: list[dict[str, Any]]  # evidence the writer may cite (from the Fit Matcher)
    # decisions
    decision: dict[str, Any]      # BidDecision
    price: dict[str, Any]         # PriceQuote
    # drafting loop
    draft: dict[str, Any]         # ProposalDraft
    verification: dict[str, Any]  # claim verification report (before/after rates)
    critiques: Annotated[list[dict[str, Any]], operator.add]
    revisions: int
    revision_request: dict[str, Any]  # user's "regenerate paragraph" request
    compliance: dict[str, Any]    # ComplianceVerdict
    preview: dict[str, Any]       # dry_run preview from the marketplace server
    # human in the loop
    approval: dict[str, Any]
    edits: Annotated[list[dict[str, Any]], operator.add]
    # results
    submission: dict[str, Any]
    outcome: dict[str, Any]
    status: str                   # analysing | skipped | watching | awaiting_approval | submitted | rejected | blocked | needs_attention | dead_letter
    status_reason: str
    # budgets and bookkeeping (reducers: parallel branches each add)
    steps: Annotated[int, operator.add]
    tokens: Annotated[int, operator.add]
    cost_usd: Annotated[float, operator.add]
    node_log: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]
    meta: Annotated[dict[str, Any], merge_dicts]


class ConversationState(TypedDict, total=False):
    user_id: str
    persona: str
    thread_id: str               # marketplace thread id
    trace_id: str
    job: dict[str, Any]
    proposal: dict[str, Any]
    messages: list[dict[str, Any]]
    new_message: dict[str, Any]
    intent: dict[str, Any]        # MessageIntent
    slots: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    reply: dict[str, Any]         # ReplyDraft
    compliance: dict[str, Any]
    preview: dict[str, Any]
    approval: dict[str, Any]
    edits: Annotated[list[dict[str, Any]], operator.add]
    sent: dict[str, Any]
    hold: dict[str, Any]
    status: str
    status_reason: str
    steps: Annotated[int, operator.add]
    tokens: Annotated[int, operator.add]
    cost_usd: Annotated[float, operator.add]
    node_log: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]
    meta: Annotated[dict[str, Any], merge_dicts]
