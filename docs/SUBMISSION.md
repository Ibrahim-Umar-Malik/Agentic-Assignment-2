# Submission checklist (steps that need your accounts)

Everything that can be built without your accounts is in the repo. These steps are yours, in this order.

1. **Merge and publish the repo.** Merge the PR into `main`, set `main` as the default branch, and make the repository
   public (Settings → General → Danger zone → Change visibility).
2. **Deploy** (about 20 minutes). The one-container build is `infra/docker/Dockerfile.allinone`.
   - Create a free Postgres database on Neon or Supabase and copy its URL.
   - On Render, create a Web Service from the repo with Docker, pointing at `infra/docker/Dockerfile.allinone`, on port 8080 with health check `/healthz` (full steps in `docs/RUNBOOK.md`).
   - Set these environment variables as secrets: `DATABASE_URL`, `GROQ_API_KEY`, `TOKEN_ENCRYPTION_KEY`
     (generate it with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`),
     `MCP_SHARED_SECRET` (any long random string), `REVIEWER_EMAIL`, `REVIEWER_PASSWORD`, and `GIGBID_PROFILE=open`.
   - Open the URL, sign in as the reviewer, and check the inbox fills within a minute.
   - Use a free uptime pinger (for example UptimeRobot, every 10 minutes) so the free instance does not sleep while
     it is being marked.
3. **Reviewer login.** Put `REVIEWER_EMAIL` / `REVIEWER_PASSWORD` in a *private* comment on GCR. Never put them in the repo.
4. **Real-model evals** (optional but recommended): with `GROQ_API_KEY` exported, run `make eval-llm && make report`,
   then commit the new `evals/results/*.json` and the rebuilt PDF.
5. **Judge labels.** Fill the `human_overall_1to5` column in `evals/datasets/judge_labels.csv` (30 drafts, 1–5), then run
   `python -m evals.runners.judge_calibration score && make tables report`.
6. **Video.** Record from `docs/VIDEO_SCRIPT.md` (3:00), upload it as Unlisted, and test the link in a private window.
7. **Portfolio MCP server.** Publish it from the public repo. Either use the uvx command from `mcp_servers/portfolio/README.md`
   (it works as soon as the repo is public),
   or push the Docker image and list it on an MCP registry. Put that link in the form.
8. **Write-up.** Publish `docs/writeup.md` on Medium or LinkedIn and add the link to the README.
9. **Upwork.** If you have API access, connect it in Settings and run `python scripts/upwork_list_tools.py`.
   Otherwise the adapter stays on its documented stub, which the report already says.
10. **Label audit** (optional, strengthens report §2): fill `human_kind` / `human_bid` for the 45 rows in
    `evals/datasets/label_audit.csv` to measure how often the silver labels on real jobs are right.
11. **Submit together:** the report PDF, deployed URL, public repo link, video link, MCP server link, write-up link, and
    `gigbid-source.zip` (rebuild it with `make zip` after any change).
