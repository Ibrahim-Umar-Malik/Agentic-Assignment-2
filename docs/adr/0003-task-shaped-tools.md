# ADR 0003: Task-shaped MCP tools

Status: accepted (Nov 2026)

## Context
Tools can mirror API endpoints (fine-grained), be one mega-tool with an action argument, or match the agent's tasks.

## Decision
Ship task-shaped tools (`search_evidence`, `get_client_history`, `get_market_stats` ...), with dry-run on every write and idempotency keys.

## Consequences
Measured in R&D question A (`evals/results/tool_granularity.json`): task-shaped tools need about half the calls per task of fine-grained ones and less than half their schema tokens. The mega-tool is smallest but hides argument schemas, which makes arguments unvalidated.
