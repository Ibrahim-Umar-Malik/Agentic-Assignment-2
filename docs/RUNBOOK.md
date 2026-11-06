# Runbook

## Run it

| Goal | Command |
|---|---|
| Everything in Docker (Postgres/pgvector, Redis, 3 MCP servers, worker, API, web, GigSim) | `cp .env.example .env` (fill it), `docker compose up --build`, open http://localhost:8080 |
| Add local open-weight models | `docker compose --profile local-llm up` and `GIGBID_PROFILE=open_local` |
| One process, no Docker | `make install && make dev` (GigSim stand-in + API + built UI on :8080, in-process MCP) |
| Tests | `make test`, `make e2e`, `make lint`, `make checks` |
| Evaluations | `make eval` (offline, no keys) · `make eval-llm` (needs `GROQ_API_KEY`) |

## Deploy (free tier)

The single-container image is `infra/docker/Dockerfile.allinone`.

1. Create a free Postgres (Neon or Supabase) and copy its URL.
2. On Render (or Railway / Fly / Koyeb): new Web Service from this GitHub repo, Docker, Dockerfile path
   `infra/docker/Dockerfile.allinone`, port 8080, health check `/healthz`.
3. Set environment variables (never in the repo): `DATABASE_URL=postgresql+psycopg://...`,
   `GROQ_API_KEY`, `TOKEN_ENCRYPTION_KEY` (Fernet key), `MCP_SHARED_SECRET`, `REVIEWER_EMAIL`,
   `REVIEWER_PASSWORD`, `REVIEWER_PERSONA=ai_ml`, `PUBLIC_BASE_URL=https://<your-app>`,
   `CORS_ORIGINS=https://<your-app>`, `GIGSIM_POLICY_VERSION=2`.
4. On start the API creates the reviewer account from those variables, already onboarded with the persona.
   Share the login only in the private GCR comment.
5. Keep it live: free instances sleep; an uptime pinger on `/healthz` every 10 minutes keeps it warm.

## Schedules (why these intervals)

| Mode | Interval | Why |
|---|---|---|
| GigSim saved searches | every 30 min (`scheduling.gigsim_scout_interval_min`) | simulator releases jobs gradually; well under its 120 req/min limit |
| Live Upwork | every 240 min (`scheduling.live_scout_interval_min`) | official API etiquette: four reads a day per saved search is enough for a freelancer, keeps us far from any rate limit and avoids looking like automation; nothing is ever sent without the user |
| Pipeline sync (events, messages) | every 2 min in the worker cron, GigSim only | cheap reads; live mode follows the 240-min rule |

Jobs are idempotent: Arq job ids are `analyze:{user}:{job}`, the jobs table claim is atomic, and every write
carries an idempotency key, so a worker restart never double-analyses or double-submits.

## Failure modes

| Symptom | Meaning | What to do |
|---|---|---|
| Yellow "Marketplace unavailable" banner | GigSim / Upwork unreachable or 5xx after retries | nothing is lost; pending approvals stay; scouting resumes automatically. Check `docker compose logs marketplace-mcp gigsim` |
| Job stuck in "needs attention" | node failed after retries or budget exceeded | open the run's trace (Agent runs → run → trace); re-run from the job page; the `dead_letter` table has the error |
| Approval decided but nothing happened | worker died between decision and resume | on restart `recover_decided` completes it; idempotency keys stop double submits |
| 429 from GigSim | rate limit | adapter waits for `Retry-After`; lower saved-search frequency |
| Upwork "not connected" | token missing / expired | Settings → Connect Upwork (refresh is automatic while the refresh token is valid) |
| Model provider down | node falls back to the profile's fallback model, then to the heuristic | runs continue, quality drops; check `/api/health` → profile |

## Budgets (declared in `agent/config.yaml: budgets`)

p95 latency per job analysed and USD per job / per proposal are declared there and measured in
`evals/results/decision.json` and on the Analytics page. Per-thread step cap 40, token cap 60,000.

## Secrets

Only from environment variables. `TOKEN_ENCRYPTION_KEY` encrypts OAuth tokens at rest; rotate by setting a new
key and asking users to reconnect. CI scans every tracked file (`scripts/check_secrets.py`).
