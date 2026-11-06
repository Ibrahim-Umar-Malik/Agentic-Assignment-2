# ADR 0002: One marketplace port, two adapters, behind our own MCP server

Status: accepted (Nov 2026)

## Context
GigSim and the official Upwork MCP server have different shapes; agents must not know which one is live.

## Decision
`agent/marketplace_port.py` is the only interface. `mcp_servers/marketplace` exposes task-shaped tools that call the port; `adapters/gigsim.py` and `adapters/upwork_live.py` implement it. Mode is configuration.

## Consequences
Swapping marketplaces touches one adapter file. The policy-v2 change request needed no adapter change at all (see report §6).
