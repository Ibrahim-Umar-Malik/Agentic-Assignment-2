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
6. **The whole system was tuned to data its author wrote.** The first build used synthetic jobs written by the
   same AI that wrote the agents. It scored a bid F1 of 0.93 there and 0.11 on real Upwork posts, where it bid on
   3 of 50 jobs it should have. The synthetic posts named skills exactly as the portfolio did; real clients write
   "Machine Learning", not "LightGBM". Caught only because Ibrahim supplied real datasets (report §9).
7. **A first silver-label rule credited skills the portfolio could not prove.** The hand-written list of tags a
   persona "can claim" included NumPy and Keras, which no portfolio project shows. A job could then be labelled
   "bid" while the Writer had no evidence to cite. Caught while reading tune-split misses; the rule now keeps a tag
   only if it appears in the portfolio text (`data_pipeline/tag_competence.py`). The label change was made once,
   from tune-split examples, and is disclosed in the data card.
8. **Scam rules that fired on ordinary work.** The rules flagged any post mentioning Telegram, Discord or crypto:
   2.9% of 5,000 real posts, mostly bot-building and crypto-product jobs. They also missed every "earn $5,000 a
   week" fraud in an external benchmark. Both were measured, not guessed (`evals/results/risk_real.json`).
