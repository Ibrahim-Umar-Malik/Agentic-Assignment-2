# ADR 0004: Ship requirement decomposition + reranking over structured chunks

Status: accepted (Nov 2026)

## Context
Nine retrieval variants were built; the shipped one must be chosen by measurement, not taste.

## Decision
A selection rule was fixed before looking at the test split (best nDCG@5 on the tune split, then MRR, then latency). It picked `v3_rerank_v1_decompose`.

## Consequences
Outcome boosting (V4) and multi-vector grouping (V5) hurt retrieval metrics and are not shipped; see `evals/results/rag.json` and `ablation.json`. Retrieval runs with a dependency-free hash embedder and lexical reranker in this build; the open-weight embedder (bge-small) is a config switch.
