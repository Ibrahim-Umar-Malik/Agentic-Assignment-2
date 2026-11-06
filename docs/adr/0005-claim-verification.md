# ADR 0005: Remove unsupported claims before the Critic sees the draft

Status: accepted (Nov 2026)

## Context
Writers (heuristic or LLM) produce claims the portfolio does not support.

## Decision
Split the draft into sentences, keep only claim-like ones, ground each against evidence (skill vocabulary, numbers must appear in the cited item), remove unsupported ones; for human edits, label but block in the Compliance Guard instead of silently deleting.

## Consequences
Unsupported-claim rate drops to zero on the test split (`evals/results/decision.json`). Honest negatives such as 'I have not used X' are not treated as claims.
