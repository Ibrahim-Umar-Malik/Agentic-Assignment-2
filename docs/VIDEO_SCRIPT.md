# 3-minute demo video script

Record at 1080p, with the browser at 100% zoom and the terminal font at 16pt or larger. Run `make dev` first, sign in
with the reviewer account, and open a second terminal for `make demo`. The timings add up to 3:00, so keep each beat short.

| Time | Screen | Say (roughly) |
|---|---|---|
| 0:00–0:15 | README hero GIF, then the Inbox | "GigBid is a freelancer copilot. Every 15 minutes it reads new job posts, skips scams and bad fits, and prepares grounded, priced proposals. Nothing is ever sent without my approval." |
| 0:15–0:35 | Architecture diagram (`docs/images/bid_graph.png`) | "Two LangGraph graphs. The bid graph goes Scout, Risk, Fit Matcher, Pricing, Decision, Writer, Critic, Compliance, then a human interrupt. Tools come from three MCP servers: GigSim, the Upwork adapter and my own Portfolio MCP server." |
| 0:35–1:10 | Inbox: open a high-fit job, then Proposal Studio | "Here is a bid. Each claim links to its evidence, so hover one to see the case study it came from. The price sits inside the client's budget. I'll edit one line and approve." Click **Approve**. Show the status changing to *submitted*. |
| 1:10–1:35 | Inbox, filter **Skipped**: the scam job | "This post asks for a deposit through Telegram. The Risk agent flagged it, so the system never drafted anything. On the test split no scam got a bid." Open the run timeline to show the risk flags. |
| 1:35–2:00 | Skipped or Watch: the injection job | "This one hides an instruction telling the agent to reveal its system prompt. The post is wrapped as untrusted data, the instruction is flagged and ignored, and the draft talks only about the job. In 19 injected tests it was obeyed zero times." |
| 2:00–2:30 | Terminal: `make demo`; then Messages | "Now I advance the simulator's clock. A client replied with a question. The conversation graph drafts an answer grounded in the same portfolio, and I approve it." Approve the reply. |
| 2:30–2:50 | Analytics page | "The analytics come from the evaluations. In simulation the reply rate is 36% against 13% for a template baseline, and the A/B test on the opening line is still running with its power stated." |
| 2:50–3:00 | README results table and GitHub repo | "Everything here is reproducible with `make eval`, and every number in the report is generated from the result files. Thanks for watching." |

## Checklist before recording
- Run `make seed` for a clean database, so the scam and injection jobs show at the top of the inbox.
- Close notifications and hide the bookmarks bar.
- Upload to YouTube as *Unlisted*, or to Google Drive with "Anyone with the link", then test the link in a private window.
