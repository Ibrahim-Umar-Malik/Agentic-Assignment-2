#!/usr/bin/env bash
# Single-container launcher: GigSim stand-in + API (serving the built web UI).
# MCP servers run in-process by default (GIGBID_MCP_INPROCESS=1) so one free-tier
# container is enough; docker compose runs them as separate services instead.
# Secrets (REVIEWER_*, GROQ_API_KEY, TOKEN_ENCRYPTION_KEY, MCP_SHARED_SECRET) come from the environment.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8080}"
GIGSIM_PORT="${GIGSIM_PORT:-8001}"
mkdir -p var
export GIGSIM_URL="${GIGSIM_URL:-http://127.0.0.1:${GIGSIM_PORT}}"
export GIGBID_MCP_INPROCESS="${GIGBID_MCP_INPROCESS:-1}"
PY="${PYTHON:-python}"
[ -x .venv/bin/python ] && PY=.venv/bin/python

"$PY" -m uvicorn gigsim_standin.app:app --host 127.0.0.1 --port "$GIGSIM_PORT" --log-level warning &
GS=$!
trap 'kill $GS 2>/dev/null || true' EXIT
for _ in $(seq 1 50); do
  curl -fs "http://127.0.0.1:${GIGSIM_PORT}/health" >/dev/null 2>&1 && break
  sleep 0.2
done
exec "$PY" -m uvicorn apps.api.main:app --host "${HOST:-0.0.0.0}" --port "$PORT" --proxy-headers --forwarded-allow-ips='*'
