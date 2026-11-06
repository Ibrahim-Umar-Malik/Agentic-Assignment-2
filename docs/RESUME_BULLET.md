# Résumé bullet

- Built **GigBid**, a LangGraph multi-agent freelancer copilot with 3 MCP servers (including a published Portfolio MCP
  server) and human approval before every send. In simulation it reached a **36.0% client reply rate vs 12.6% for a
  template baseline** (4.73 vs 1.57 replies per 100 Connects), with **0 of 19 prompt injections obeyed** and **no bids on
  17 scam posts**.
- Ran 9 retrieval variants with a pre-registered selection rule and a paired end-to-end analysis, and found that chunk
  structure, not ranking, drove a **+7.1-point reply-rate gain** (metric-quoting drafts rose from 8.1% to 65.8%). A
  claim verifier cut unsupported claims from 15.4% to 0%.

*Numbers come from `evals/results/` (offline profile, synthetic stand-in data). Rerun `make eval-llm` before quoting
them with real models.*
