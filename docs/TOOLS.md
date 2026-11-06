# Tools

Every tool an agent can reach, who may call it (allowlists: `agent/mcp_client.py`), and why it is trusted.
Schemas are snapshot-tested (`tests/contract/snapshots/*.json`); a schema change fails CI until the snapshot is
updated on purpose (`UPDATE_SNAPSHOTS=1 pytest tests/contract`). All write tools take an `idempotency_key` and
support `dry_run`; every call is written to the append-only audit log with user, arguments, result and trace id.

## Our servers

| Tool | Server | Read / write | Annotations | Called by | Trust rationale |
|---|---|---|---|---|---|
| search_jobs | marketplace | read | readOnly, idempotent | scout | Returns job posts, which are **untrusted text**: sanitised and delimited before any model sees them. |
| get_job | marketplace | read | readOnly, idempotent | scout, risk, liaison | Same: job text is data, never instructions. |
| get_client_history | marketplace | read | readOnly, idempotent | risk | Marketplace facts (spend, hires, rating, payment verification); reviews text is untrusted. |
| get_market_stats | marketplace | read | readOnly, idempotent | pricing | Aggregates over awarded jobs; no free text. |
| get_connects_balance | marketplace | read | readOnly, idempotent | pricing, executor | Number only. |
| get_policy | marketplace | read | readOnly, idempotent | pricing | Platform policy version and rules (change request v2). |
| list_messages | marketplace | read | readOnly, idempotent | liaison, sync | Client messages are untrusted text. |
| list_proposals | marketplace | read | readOnly, idempotent | sync | Status fields only. |
| list_events | marketplace | read | readOnly, idempotent | scout, sync | Status events. |
| create_proposal_draft | marketplace | write (non-destructive) | idempotent | **executor only** | Runs only after approval; dry-run preview is what the user approves. |
| submit_proposal | marketplace | write (destructive: spends Connects) | destructive, idempotent | **executor only** | Only after the approval interrupt returns "approve"; idempotency key = thread + draft version + edits. On Upwork live it creates a draft the user confirms on Upwork. |
| send_message | marketplace | write (destructive) | destructive, idempotent | **executor only** | Only after approval of that exact reply. |
| search_evidence | portfolio | read | readOnly, idempotent, closed-world | matcher, writer, verifier, critic, liaison | The freelancer's own corpus; per-user scoping; deleted items excluded. |
| get_case_study | portfolio | read | readOnly, idempotent | matcher, writer, verifier | Same corpus. |
| list_skills | portfolio | read | readOnly, idempotent | matcher, verifier | Derived from the corpus. |
| free_slots | workspace | read | readOnly, idempotent | liaison | The user's (mock) calendar. |
| create_interview_hold | workspace | write | idempotent, non-destructive | liaison (after approval of the reply) | Tentative hold on the user's own calendar only. |
| create_email_draft | workspace | write | non-destructive | liaison | Creates a draft; never sends email. |

Portfolio also exposes **resources** (`portfolio://case/{id}`, `portfolio://proposal/{id}`, `portfolio://profile`)
and **prompts** (`answer_screening_question`, `prove_requirement`, `draft_proposal_opening`).

## Official servers

| Server | Tools used | Read / write | Trust rationale |
|---|---|---|---|
| Upwork MCP (`mcp.upwork.com`) | job search, job details, client info, proposals/messages (mapped in `upwork_live.py`; real names printed by `scripts/upwork_list_tools.py`) | reads; writes only create drafts | Official API under the user's own OAuth 2.1 grant (PKCE, tokens Fernet-encrypted per user). No scraping, no browser automation. Polled at most every 240 minutes. |
| GitHub MCP | repository contents for portfolio ingestion (`rag/ingest/github.py`) | read | Read-only fine-grained token; README and code become evidence, so a repo is only ingested from the user's own account. |

## Limits

Per-user rate limiter in the marketplace server (60/min, below GigSim's 120/min); GigSim 429s are retried
after `Retry-After`; 5xx are retried with backoff and then surface as "marketplace unavailable" (degraded banner),
never as a crash.
