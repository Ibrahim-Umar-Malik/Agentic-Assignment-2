# Starter kit: what was used and how GigBid differs

The instructor's *GigBid Student Starter Kit v0.1* is a scaffold. I used it as a checklist and an interface
reference, not as code: everything here is my own implementation. This page maps each part of the kit to where
it lives in GigBid.

| Starter kit | GigBid | Notes |
|---|---|---|
| `data/sample/*.json` (2 jobs, 1 freelancer, 1 portfolio item, 1 client) | `tests/fixtures/starter_kit/` (copied unchanged) + `tests/unit/test_starter_kit_samples.py` | The kit's legitimate churn job is not flagged. Its "unpaid trial + external messaging app" job is flagged as a scam with both of the kit's warning signals (`free_work`, `off_platform`). This test caught a gap: the v2 rules missed "external messaging app" |
| Real data | `data_pipeline/` + six Kaggle datasets (`docs/DATA_CARD.md`) | The kit's sample data is "illustrative only". Jobs, clients and prices now come from real Upwork postings and contracts |
| `data/policy_pack/marketplace_policy.md` (7 rules) | `data/policy_pack/policy.md` + `rules.yaml` + `agent/nodes/compliance.py` | Kit 1 → P1 (no off-platform contact) + P2 (no off-platform payment); kit 2 → P6 (no free work); kit 3 → P3 (no fabricated claims, enforced by the claim verifier and the edit re-check); kit 4 → P4 (no guarantees); kit 5 → prompt-injection defences (sanitise, delimit, compliance); kit 6 → P5 + rate limits in the marketplace MCP server; kit 7 → LangGraph `interrupt` before every submit, send and Connects spend |
| `agent/handoffs.py` (JobSpec, RiskReport, FitReport, ProposalDraft) | `agent/handoffs.py` | Same idea, with more fields: requirement-by-evidence matrix, risk flags with severities, price rationale, claim-level evidence ids |
| `agent/marketplace_port.py` (Protocol: search_jobs, get_job, get_client_history, get_connects_balance, create_proposal_draft) | `agent/marketplace_port.py` + `mcp_servers/marketplace/adapters/{gigsim,upwork_live}.py` | All five methods are present, plus submit, messaging, market stats and policy. Idempotency keys on every write |
| `agent/graphs/bid_graph.py`, `conversation_graph.py` (placeholders) | `agent/graphs/` | Parallel analyst / risk / matcher branches, bounded critic loop, compliance guard, approval interrupt, durable checkpoints |
| `agent/nodes/*` (scout, analyst, risk_assessor, fit_matcher, pricing, writer, critic, compliance, client_liaison) | `agent/nodes/*` | Same nine roles |
| `agent/memory/promotion_rules.py` | `agent/memory/` | Episodic → semantic promotion with explicit rules |
| `mcp_servers/{portfolio,marketplace,workspace}/server.py` | `mcp_servers/{portfolio,marketplace,workspace}/` | The Portfolio server is packaged for publishing (`mcp_servers/portfolio/README.md`) |
| `rag/variants/v0_naive.py`, `rag/verify.py` | `rag/` | V0 plus eight variants; claim splitting and verification |
| `agent/config.yaml` thresholds (fit 0.60, risk 0.70) | `agent/config.yaml` (fit 0.35, risk 0.60) | Chosen by a sweep on the tune split of the real-job dev set (`evals/results/decision.json`) |
| `apps/api`, `apps/web` notes | FastAPI + React app with all screens, Playwright tests | |
| `infra/docker-compose.yml`, `.env.example`, `Makefile`, CI | `infra/`, `.env.example`, `Makefile`, `.github/workflows/` | |
| `docs/IMPLEMENTATION_CHECKLIST.md` | All items done. The ones that need accounts are in `docs/SUBMISSION.md` | |
