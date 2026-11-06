# ADR 0008: Signature extension X2: proposal A/B experiments

Status: accepted (Nov 2026)

## Context
Freelancers argue about proposal style without data.

## Decision
Stable hash assignment of each analysed job to an arm, the arm changes one Writer behaviour, outcomes are compared per arm with a two-proportion z-test, and a winner is only declared after 30 proposals per arm and p < 0.05.

## Consequences
See `docs/EXTENSION.md` and `evals/results/gigsim_outcomes.json`.
