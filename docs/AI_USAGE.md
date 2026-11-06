# AI usage

| Tool | Used for | Files |
|---|---|---|
| Claude Code (Anthropic) | scaffolding and first drafts of most code, tests, docs and eval runners, run under my direction in a cloud session; I set the requirements from the assignment brief and reviewed the results | whole repository |
| Open-weight models via Groq (`gpt-oss-20b`, `gpt-oss-120b`) | the product's own LLM nodes in the `open` profile | `agent/prompts/*.md`, `core/llm.py` |

Every number in the README and report comes from `evals/results/*.json`, produced by the runners in
`evals/runners/`; none were typed by hand (`python -m evals.make_tables --check` enforces this in CI).

## Things the AI got wrong that were caught

1. **Variant evals silently measured the same pipeline.** The Portfolio MCP server computed its retrieval
   options once at import time, so switching `GIGBID_RAG_VARIANT` in the end-to-end variant run changed nothing
   and V0 and the shipped pipeline produced byte-identical downstream numbers. Identical results for different
   variants were the tell; the fix reads the options per call (`mcp_servers/portfolio/backend.py:default_options`).
2. **A database path without ".db" deadlocked the app.** Checkpointer and memory store derived their SQLite file
   names with `.replace(".db", ...)`; for `db.sqlite` all three used one file and the API hung on a write lock.
   Found when the browser test timed out; fixed with `core/db.py:sibling_sqlite_path`.
3. **An off-domain job got a 100% fit.** "Need Django expert" listed only Python and PostgreSQL as skills; the
   matcher only looked for skills from the freelancer's own vocabulary, so Django was never a requirement. Caught
   by looking at the inbox screenshot; fixed by recognising title skills from a market vocabulary.
4. **A rewritten guarantee still blocked the draft.** The Compliance Guard rewrote "I guarantee 100% results"
   (policy P4) but still blocked on the pre-rewrite sentence as an unsupported claim. Caught by the Playwright
   edit test.
5. **An A/B experiment that could not differ.** The first experiment (question-first vs evidence-first opening)
   kept the question in both arms, so the paired difference was exactly 0.0. Redesigned as question vs no question.
