# ADR 0006: An offline model profile with deterministic heuristics

Status: accepted (Nov 2026)

## Context
CI and graders must run the system without API keys, and this build environment had no model access.

## Decision
Every LLM node has a heuristic fallback; `GIGBID_PROFILE=offline` uses only those. The `open` profile (open-weight models on Groq) and `open_local` (Ollama) use the same graph.

## Consequences
All committed numbers state their profile. Arms that need a real model (R&D A selection accuracy, R&D C ReAct/supervisor) are recorded as not run rather than guessed.
