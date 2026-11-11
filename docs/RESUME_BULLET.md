# Résumé bullet

- Built **GigBid**, a LangGraph multi-agent freelancer copilot with 3 MCP servers (including a published Portfolio
  MCP server) and human approval before every send. Rebuilt and evaluated it on **36k real Upwork job posts and 1.29M
  contracts**. Failure analysis lifted bid F1 on real posts **from 0.11 to 0.80**, with **0 of 14 prompt injections
  obeyed** and **no bids on 27 scam posts**.
- Compared 9 retrieval variants under a pre-registered selection rule, plus a paired end-to-end analysis. Found that
  chunk structure, not ranking, drove a **+8.9-point simulated reply-rate gain**; drafts quoting a metric rose from
  19% to 47%. Cut scam-rule false alarms on real posts from 2.9% to 0.4%.

*Numbers come from `evals/results/` (offline profile; real job data with synthetic portfolios and simulated
replies). Rerun `make eval-llm` before quoting them with real models.*
