# GigBid

**A freelancer's copilot that finds the right jobs, writes proposals that only claim what your portfolio proves,
and never sends anything without your approval.**

![GigBid demo: inbox to approved proposal](docs/images/demo.gif)

**Live app:** see the GCR submission (reviewer login shared privately) · **Demo video (3 min):** see the GCR submission ·
**Portfolio MCP server:** [`mcp_servers/portfolio`](mcp_servers/portfolio/README.md) · **R&D report:** [`docs/report/GigBid_RnD_Report.pdf`](docs/report/GigBid_RnD_Report.pdf) ·
**Write-up:** [`docs/writeup.md`](docs/writeup.md)

## What it does in two minutes

1. **Scouts** your saved searches on a schedule (GigSim, or your real Upwork account through Upwork's official MCP server).
2. For each job, three agents run **in parallel**: a Job Analyst (what the client really needs), a Risk Assessor
   (scams, bad clients, prompt injection hidden in the post) and a Fit Matcher (which of your projects prove each requirement).
3. It decides **bid, watch or skip**, prices the bid from market data and your floor, and checks whether the Connects are worth it.
4. A Writer drafts the proposal from your evidence; **every claim is checked** against your portfolio and unsupported ones are
   removed; a Critic sends it back at most twice; a Compliance Guard enforces the platform's policy pack.
5. **You approve, edit, regenerate a paragraph or reject** in the Proposal Studio. Hover any sentence to see the evidence behind it.
   Approval survives a server restart; a crash never submits twice.
6. When a client replies, a Client Liaison classifies the message (question, negotiation, interview, scam) and drafts a reply and
   interview slots, again for your approval.

## Architecture

![bid graph](docs/images/bid_graph.png)

Two LangGraph graphs (bid: one thread per job; conversation: one thread per client thread) talk to five MCP servers:
our own **Marketplace** (one port, GigSim and Upwork-live adapters), **Portfolio** (advanced RAG, published separately) and
**Workspace** (calendar holds, email drafts), plus the official **Upwork** and **GitHub** servers. FastAPI + React (Vite, TS)
on top, Arq worker for schedules, Postgres + Redis underneath. Details: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Results

All numbers below are rendered from [`evals/results/`](evals/results) by `python -m evals.make_tables` (CI fails if they drift).

**Data.** Job posts, client signals and market prices are **real**. They come from six public Kaggle datasets
(36,265 cleaned Upwork posts, 1.29M contracts). The three freelancer portfolios, client reply behaviour and the
planted scams and injections are **synthetic** and labelled as such on every record. Details, licences and
limitations: [`docs/DATA_CARD.md`](docs/DATA_CARD.md), [`data/real/README.md`](data/real/README.md). All runs use
the `offline` model profile (deterministic heuristics in every LLM node) and a hash embedder. `make eval-llm`
reruns everything with open-weight models.

### What changed when the data became real

<!-- table:shift -->
| Test split (180 jobs each) | Bid/skip accuracy | Bid F1 | Bid recall | Scams not bid on | Injections obeyed | Price in fair band |
|---|---|---|---|---|---|---|
| Synthetic jobs, old code | 91.7% | 0.928 | 0.924 | 100.0% of 17 | 0 of 19 | 84.6% |
| **Real jobs, old code** | 73.3% | 0.111 | 0.060 | 100.0% of 27 | 0 of 14 | 100.0% |
| Real jobs, after fixes | 89.4% | 0.800 | 0.760 | 100.0% of 27 | 0 of 14 | 88.9% |

Evidence retrieval (V0 naive, test split): Recall@5 0.922 on synthetic jobs vs 0.516 on real jobs.
<!-- /table:shift -->

The first version was built and tuned on synthetic jobs. On real Upwork posts it skipped almost every good job.
The failure analysis and fixes are in report §9.

### Retrieval: variants compared on the tune split, shipped choice reported on the test split

<!-- table:rag -->
| Variant (tune split) | Recall@5 | MRR | nDCG@5 | p95 ms |
|---|---|---|---|---|
| v0_naive | 0.498 | 0.547 | 0.447 | 7.5 |
| v1_decompose | 0.513 | 0.505 | 0.430 | 4.7 |
| v2_hybrid | 0.503 | 0.552 | 0.456 | 8.4 |
| v3_rerank | 0.487 | 0.494 | 0.423 | 8.9 |
| v4_outcome | 0.518 | 0.521 | 0.444 | 6.3 |
| v5_multivector | 0.421 | 0.383 | 0.316 | 15.6 |
| v6_contextual | 0.511 | 0.566 | 0.471 | 6.2 |
| v7_hyde | 0.607 | 0.627 | 0.537 | 5.4 |
| v8_corrective | 0.559 | 0.560 | 0.480 | 5.2 |
| v2_hybrid_v1_decompose | 0.531 | 0.520 | 0.445 | 4.7 |
| v3_rerank_v1_decompose | 0.535 | 0.532 | 0.453 | 11.5 |
| v2_hybrid_v1_decompose_v4_outcome | 0.519 | 0.484 | 0.425 | 3.9 |
| v2_hybrid_v1_decompose_v3_rerank_v4_outcome | 0.541 | 0.496 | 0.442 | 11.4 |
| v6_contextual_v2_hybrid_v1_decompose_v4_outcome | 0.513 | 0.501 | 0.430 | 5.0 |
| v8_corrective_v2_hybrid_v1_decompose_v4_outcome | 0.543 | 0.529 | 0.461 | 6.6 |
| **v7_hyde_v2_hybrid** | 0.654 | 0.696 | 0.601 | 6.0 |
| v7_hyde_v2_hybrid_v6_contextual | 0.644 | 0.692 | 0.599 | 6.9 |

Chosen by rule (max nDCG@5 on tune split (2 dp), then MRR, then lower p95 latency): **v7_hyde_v2_hybrid**. Held-out test split: nDCG@5 0.582 vs naive 0.450; Recall@5 0.626 (95% CI [0.5645, 0.6901]) vs 0.516. Embedder `hash`, reranker `lexical`, commit `9ba9cd9`.
<!-- /table:rag -->

### End to end: naive retrieval vs shipped, through the whole bid graph (test split)

<!-- table:b5 -->
| Variant | Evidence Recall@5 | nDCG@10 | Unsupported claims / proposal | Judge score | GigSim reply rate | p95 latency (s) | Cost / proposal (USD) |
|---|---|---|---|---|---|---|---|
| V0 naive | 0.516 | 0.453 | 0.00 (0.30 before verify) | 3.66 | 26.0% | 0.39 | $0.0000 |
| **Shipped: v7_hyde_v2_hybrid** | 0.626 | 0.602 | 0.00 (0.26 before verify) | 4.00 | 34.9% | 0.43 | $0.0000 |

Paired on the same 47 proposals: the lead evidence changed in only 10, yet reply probability rose +8.2 points on the proposals whose lead evidence did *not* change. Drafts quoting a specific metric: 19.1% with V0 vs 46.8% shipped.
<!-- /table:b5 -->

### Decisions, safety and grounding (test split)

<!-- table:decision -->
| Metric (test split, n=180, profile `offline`) | Value |
|---|---|
| Bid/skip accuracy | 89.4% (95% CI [84.4, 93.3]) |
| Bid precision / recall / F1 | 0.844 / 0.760 / 0.800 |
| Scam posts not bid on | 100.0% of 27 |
| Injected posts flagged / obeyed | 100.0% flagged, 0 of 14 obeyed |
| Unsupported claims without verifier → shipped | 11.8% → 0.0% (102 claims) |
| Bids inside the fair price band | 88.9% of 45 |
| Latency per job p50 / p95 | 0.26s / 0.45s |
| Errors | 0 of 180 |

Thresholds chosen on the tune split by F1: bid_min_fit=0.35, max_risk=0.6 (tune F1 0.8308).
<!-- /table:decision -->

### Outcomes in GigSim vs common baselines (test split)

<!-- table:outcomes -->
| System (180 test jobs) | Bids | Connects | Reply rate | Replies / 100 Connects | Interviews | Hires | Scam bids |
|---|---|---|---|---|---|---|---|
| **GigBid** | 47 | 257 | 36.0% | 6.58 | 10.8 | 5.4 | 0 |
| Template, bid on all | 115 | 587 | 11.2% | 2.20 | 6.7 | 2.7 | 5 |
| Reuse best past proposal | 180 | 861 | 11.7% | 2.44 | 11.2 | 4.7 | 27 |
<!-- /table:outcomes -->

### Multi-agent comparison (R&D question C)

<!-- table:arch -->
| Architecture (50 jobs) | Decision accuracy | Scam bids | Unsupported claims (independent re-check) | Tool calls / job | p95 latency |
|---|---|---|---|---|---|
| graph | 92.0% | 0 | 6.2% | 10.0 | 0.45s |
| react | not run: needs an LLM |  |  |  |  |
| supervisor | not run: needs an LLM |  |  |  |  |
<!-- /table:arch -->

### Signature extension: proposal A/B experiments (X2)

<!-- table:ab -->
| X2 experiment: ask one clarifying question vs close with a next step | Value |
|---|---|
| Jobs (paired, both arms written) | 47 |
| Reply probability: statement / question | 27.2% / 32.9% |
| Paired lift (question − statement) | +5.8 points (95% CI [4.3, 7.3]) |
| Chance the live z-test calls it at 30 / 120 / 500 proposals per arm | 10.0% / 20.0% / 47.5% |
<!-- /table:ab -->

## Public traces

Each is the full execution trace (every node, tool call, arguments, tokens, cost, latency; PII masked):

* [Skipped scam](docs/traces/scam_skipped.json)
* [Approved proposal (inbox → submitted)](docs/traces/approved_proposal.json)
* [Critic loop (draft sent back, then approved)](docs/traces/critic_loop.json)
* [Crash and resume (submitted exactly once)](docs/traces/crash_resume.json)

On the live app the same traces are public at `/share/trace/<trace id>` (no login needed).

## Run it

```bash
cp .env.example .env            # fill in secrets; never commit .env
docker compose up --build       # web on http://localhost:8080 (Postgres, Redis, 3 MCP servers, worker, GigSim)
# or, without Docker:
make install && make dev        # single process on :8080
make test && make e2e           # unit, contract, integration, Playwright
make data                       # optional: rebuild data from Kaggle (needs the [data] extra)
make eval                       # every number in this README
```

Deploying for free, schedules and failure handling: [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

## Repository map

| Path | What |
|---|---|
| `agent/` | graphs, nodes, Pydantic hand-offs, versioned prompts (`agent/prompts/*.md`), memory promotion rules, MCP client + allowlists, `config.yaml` |
| `rag/` | ingestion (PDF, Markdown, repos via GitHub MCP), chunkers, hybrid index, 9 variants, claim verification |
| `mcp_servers/` | marketplace (GigSim + Upwork live adapters), portfolio (published), workspace |
| `apps/api`, `apps/web` | FastAPI (auth, SSE streaming, approvals, encrypted OAuth vault) and React + TS UI, Playwright specs |
| `worker/` | Arq: scheduled scouting, analyses, resume-after-approval, pipeline sync |
| `gigsim/`, `gigsim_standin/` | reserved for the official simulator; the stand-in simulator, seeded with real jobs, clients and prices |
| `data_pipeline/`, `data/real/` | Kaggle → cleaned, PII-scrubbed, categorised jobs, market prices, silver labels (`make data`) |
| `evals/` | dev sets (real jobs), runners, committed results |
| `docs/` | architecture, ADRs, data card, tools, runbook, extension, AI usage, report |

## Pinned versions

Python 3.12, LangGraph 1.2.20, langchain-core 1.7.6, langchain-mcp-adapters 0.3.2, MCP SDK 1.30.0, FastAPI 0.162.0,
SQLAlchemy 2.0.44, Arq 0.28.0; React 18.3.1, Vite 5.4.11, TypeScript 5.6.3, Playwright 1.56.1 (full list in `pyproject.toml`
and `apps/web/package.json`). Models (open profile): `openai/gpt-oss-20b` and `openai/gpt-oss-120b` on Groq, fallback
`qwen/qwen3-32b`; local: `qwen3:8b` on Ollama.

## Safety

GigBid never sends a proposal or message without an explicit approval, never scrapes or automates a browser on Upwork, treats
job posts and client messages as untrusted data, masks contact and payment details in logs and traces, encrypts OAuth tokens and
scopes every query by user. See report §9.
