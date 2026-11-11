# My agent scored 0.93 on data I wrote and 0.11 on real job posts

*What 36,000 real Upwork posts did to a multi-agent system tuned on synthetic data, and the one result that survived.*

For a university R&D assignment I built GigBid, a copilot for freelancers on marketplaces like Upwork. It reads new
job posts on a schedule and skips scams and bad fits. For the good ones, it prepares a priced proposal grounded in
the freelancer's portfolio. A human approves every proposal before anything is sent. Under the hood it is two
LangGraph graphs, three MCP servers and a retrieval pipeline over the portfolio.

No data came with the assignment at first, so I generated it: three freelancer personas, a few hundred clients,
600 labelled job posts with planted scams and prompt injections, and a marketplace simulator. I tuned everything on
that. On the held-out test split the bid/skip decision reached an F1 of 0.93, with no scam bid on and no injection
obeyed. Then real data arrived, and the same code scored 0.11.

This is about what broke, what the fixes were, and the one finding from the synthetic build that survived.

## The setup that made it look good

GigBid decides to bid when a Fit Matcher finds portfolio evidence for the job's requirements and a Risk Assessor
finds nothing alarming. The thresholds (fit at least 0.70, risk at most 0.35) were chosen by a sweep on a tune split.
I wrote down the selection rules before running anything and touched the test split once. That is the textbook
protocol, and it was not enough.

The problem was upstream of the protocol. I had written the job generator, the personas and the agents, so they
shared a vocabulary. A synthetic post asked for "LangGraph, pgvector and FastAPI"; the synthetic portfolio said
"LangGraph, pgvector and FastAPI". Fit scores were high because the two sides were literally made of the same words.

## The real data

The rebuilt dev set uses 36,265 cleaned posts from a public Upwork dataset, with titles, descriptions, the client's
own skill tags, budgets, Connects and client history. Market prices come from 1.29 million real freelance contracts.
The portfolios are still synthetic: no public dataset has freelancers' case studies, code and past proposals. Labels
are rules over the client's tags and the skills the portfolio can prove. The planted scams and injections are still
synthetic overlays on real posts, because safety metrics need known ground truth.

The old code on the new data kept its safety record: no scam was bid on and no injection obeyed. But of the 50 test
jobs it should have bid on, it bid on 3. Accuracy looked fine at 73%, because skipping is usually right. F1 told the
truth.

## Why it failed

Failure analysis on the tune split found four causes, none of them visible on synthetic data.

**Real clients tag umbrella skills.** A real post for a churn model is tagged "Machine Learning", "Data Science",
"Artificial Intelligence". The portfolio says "LightGBM", "pandas", "scikit-learn". The matcher treated each tag as
a requirement and looked for it in the evidence. It found nothing, so fit came out at 0.07 to 0.20 for jobs the
persona plainly fits. The fix was an umbrella-tag ontology built from the most common real tags, so evidence for a
specific skill counts for the umbrella over it.

**My price floors were invented.** I had given the personas floors of $40–45 an hour. The median paid rate in their
categories, from the contracts data, is $21–30. Jobs a typical freelancer would take were skipped as "below floor".

**My scam rules were written against my own scams.** On synthetic data they caught every scam with no false alarms.
On 5,000 real posts they flagged 2.9% as scams, mostly Telegram bots, Discord bots and crypto products: legitimate
work that merely mentions those words. An external fake-job dataset showed the opposite failure. The rules caught
none of its "earn $5,000 a week, no experience, contact now" frauds, a type my generator had never produced.
Rules that need an *ask* ("contact me on Telegram", "pay in crypto"), plus an income-scam rule, brought false alarms
to 0.4% and benchmark recall to 81%.

**Market prices are not job prices.** Pricing from the category's market band under-bid real jobs badly, for example
$270 on a $4,000 post. Most real contracts are small, so the market's interquartile range sits far below the budget
of any substantial post. Quoting a fit-dependent share of the client's own budget fixed most of it.

After those fixes and a threshold re-sweep on the real tune split, test F1 is 0.80 with precision 0.84 and recall
0.76. Accuracy is 89%, scams are still all caught, and no injection was obeyed. Not 0.93, but it is a number about
the world rather than about my generator.

## The finding that survived

On synthetic data I had found something I wrote up at the time. A better retriever raised the simulated reply rate
by 7 points, but not because it found better evidence. Pairing the drafts showed the lead project rarely changed.
What changed was the *chunk*: fixed 512-token chunks cut case studies before their "Result" section, so the writer
had no number to quote. Structured chunks keep problem, approach and result together.

I expected this to evaporate on real data, since it came from a synthetic world. It did not.

On real posts the retrieval winner changed: HyDE plus hybrid search, not decomposition plus reranking. Retrieval is
much harder (Recall@5 for the naive pipeline fell from 0.92 to 0.52, because real posts describe problems in the
client's words, not the portfolio's). The shipped pipeline lifted Recall@5 to 0.63, and the simulated reply rate
rose from 26.0% to 34.9%. Paired on the same 47 proposals, the lead evidence changed in only 10. On the proposals
whose lead evidence did *not* change, reply probability still rose 8.2 points. Drafts quoting a specific metric went
from 19% to 47%. In the ablation, switching structured chunking off is now the single most damaging change (−0.06
nDCG@5).

So the mechanism held: chunk boundaries decide what a writer can quote, and ranking metrics cannot see it.

## What I would tell someone building agents on synthetic data

**Your generator and your system share a vocabulary.** If one author (or one model) writes both, matching is easy
by construction. The first real-data run will tell you how much of your score was that shared vocabulary.

**Measure rules on real text, both ways.** Precision on real legitimate text and recall on real fraud are separate
measurements, and synthetic data gives you neither. My scam rules were perfect on synthetic data and wrong in both
directions on real data.

**Ground parameters in data you did not write.** Every number I had chosen by intuition (floors, fixed-price
minimums, thresholds) was wrong in the same direction: tuned to a cleaner, richer world than the real one.

**Keep the protocol anyway.** The tune/test discipline did not prevent the failure, but it made it measurable.
Because every fix was chosen on the tune split, the 0.80 means something.

**Pair your comparisons.** The chunking finding only appeared by pairing proposals for the same job. It survived a
complete change of data, which is the best evidence I have that it is real.

## Limits

The portfolios and the simulator's reply model are still mine, so reply rates are still circular: they show that
GigBid optimises what my simulator rewards. The labels on real jobs are rules, not human judgments, and a 45-row
audit sheet is waiting for a human. Every run used deterministic heuristic agents instead of LLMs, because the build
environment had no model access. An LLM matcher might bridge "Machine Learning" to "LightGBM" on its own, though
retrieval and labels would still need the ontology. All numbers here come from files in the repository's
`evals/results/` folder, and the runs with real models are one command away.
