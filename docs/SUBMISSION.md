# Submission checklist (steps that need your accounts)

Everything that can be built without your accounts is in the repo.

**Done (2026-11-11):**
- The repository is public and `main` is the default branch at the latest commit.
- The app is deployed on Render at https://gigbid-m8kt.onrender.com: one Docker web service
  (`infra/docker/Dockerfile.allinone`, health check `/healthz`) plus a free Render Postgres database. Secrets
  (`DATABASE_URL`, `TOKEN_ENCRYPTION_KEY`, `MCP_SHARED_SECRET`, `REVIEWER_EMAIL`, `REVIEWER_PASSWORD`) are set on
  Render only. It runs `GIGBID_PROFILE=offline` (heuristic agents) because no `GROQ_API_KEY` was available; add
  that key on Render and set `GIGBID_PROFILE=open` to switch to open-weight models. Pushes to `main` redeploy it.
- The Portfolio MCP server installs from the public repo with the uvx command in `mcp_servers/portfolio/README.md`
  (checked: it starts and lists its three tools).
- The free Render Postgres expires on 2026-12-11. That is after marking, but upgrade it or move `DATABASE_URL` to Neon if
  the app must stay up longer.

**Still yours, in this order:**

1. **Reviewer login.** Put `REVIEWER_EMAIL` / `REVIEWER_PASSWORD` (sent to you privately, not in this repo) in a
   *private* comment on GCR.
2. **Video.** Record from `docs/VIDEO_SCRIPT.md` (3:00), upload it as Unlisted, and test the link in a private window.
3. **Write-up.** Optionally publish `docs/writeup.md` on Medium or LinkedIn and add the link to the README. Otherwise
   submit the GitHub link: https://github.com/Ibrahim-Umar-Malik/Agentic-Assignment-2/blob/main/docs/writeup.md
4. **Portfolio MCP server link:** https://github.com/Ibrahim-Umar-Malik/Agentic-Assignment-2/tree/main/mcp_servers/portfolio
   (optionally also list it on an MCP registry).
5. **Real-model evals** (optional but recommended): with `GROQ_API_KEY` exported, run `make eval-llm && make report`,
   then commit the new `evals/results/*.json` and the rebuilt PDF.
6. **Judge labels** (optional): fill the `human_overall_1to5` column in `evals/datasets/judge_labels.csv` (30 drafts, 1–5),
   then run `python -m evals.runners.judge_calibration score && make tables report`.
7. **Label audit** (optional, strengthens report §2): fill `human_kind` / `human_bid` for the 45 rows in
   `evals/datasets/label_audit.csv` to measure how often the silver labels on real jobs are right.
8. **Upwork** (optional): if you have API access, connect it in Settings and run `python scripts/upwork_list_tools.py`.
   Otherwise the adapter stays on its documented stub, which the report already says.
9. **Keep it awake while it is marked:** a free uptime pinger (for example UptimeRobot) on
   https://gigbid-m8kt.onrender.com/healthz every 10 minutes.
10. **Submit together:** the report PDF, https://gigbid-m8kt.onrender.com, https://github.com/Ibrahim-Umar-Malik/Agentic-Assignment-2,
    the video link, the MCP server link, the write-up link, and `gigbid-source.zip` (rebuild it with `make zip` after any change).
