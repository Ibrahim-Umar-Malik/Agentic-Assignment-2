# ADR 0007: Compose for the full stack, one container for free hosting

Status: accepted (Nov 2026)

## Context
The full stack has nine services; free hosts give one container.

## Decision
`infra/docker-compose.yml` runs everything separately (Postgres/pgvector, Redis, three MCP servers, worker, API, web, optional Ollama). `infra/docker/Dockerfile.allinone` runs GigSim stand-in + API + built UI in one process with in-process MCP sessions and an inline scheduler.

## Consequences
Same code paths; MCP calls are in-memory sessions instead of HTTP in the single container. Data persists if `DATABASE_URL` points at a managed Postgres.
