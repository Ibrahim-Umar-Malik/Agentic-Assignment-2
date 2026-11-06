# ADR 0001: Hand-written StateGraph instead of a ReAct agent or prebuilt supervisor

Status: accepted (Nov 2026)

## Context
The bid flow has hard ordering rules (risk before writing, verification before critique, approval before any write) and must pause, resume after a crash and explain every decision.

## Decision
Build two explicit LangGraph `StateGraph`s (bid, conversation) with typed state, `Send` for the three parallel analyses, a deferred decision node, a bounded Critic loop and an `interrupt()` for approval.

## Consequences
Ordering and the human gate are structural, not prompt-dependent. Cost: more code than `create_react_agent`. R&D question C (`evals/results/architecture_compare.json`) measures whether this is worth it.
