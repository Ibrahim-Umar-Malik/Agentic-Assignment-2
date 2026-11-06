# My retrieval got 3% better and my reply rate 7 points better. Retrieval was not the reason.

*What building a multi-agent proposal writer taught me about measuring RAG by what it buys downstream.*

For a university R&D assignment I built GigBid, a copilot for freelancers on marketplaces like Upwork. It reads new
job posts on a schedule, skips scams and bad fits, and for the good ones prepares a priced proposal grounded in the
freelancer's own portfolio: case studies, repositories, past proposals and client reviews. A human approves every
proposal before anything is sent. Under the hood it is two LangGraph graphs, a handful of MCP servers and a
retrieval pipeline over the portfolio.

The assignment asked for something I assumed would be the boring part: build at least four retrieval variants,
compare them, and ship the best. I built nine. The interesting result was not which one won. It was that the metric
I used to pick the winner was measuring the wrong thing, and the real effect was hiding in a detail none of my
retrieval metrics could see.

## The setup

Each test job lists requirements ("LangGraph", "RAG evaluation", "Postgres"). The Fit Matcher agent asks the
Portfolio MCP server for evidence per requirement and builds a requirement-by-evidence matrix. The Writer drafts
from that evidence, a verifier deletes any claim the evidence does not support, a Critic can send the draft back
twice, and a Compliance Guard enforces the platform's rules. Outcomes come from a marketplace simulator whose
simulated clients reply, interview and hire based on preferences the agent never sees.

The retrieval variants were the usual menu: a naive baseline (fixed 512-token chunks, dense search), requirement
decomposition, hybrid BM25 + dense with reciprocal rank fusion, reranking, an "outcome boost" that prefers evidence
from proposals that won, multi-vector indexing, contextual chunk headers, HyDE and a corrective loop. Every dev job
has gold labels for which portfolio projects genuinely evidence it, so I could score Recall@5, MRR and nDCG.

Before running anything I wrote down a selection rule (best nDCG@5 on a tune split, ties broken by MRR then latency)
and a hypothesis: decomposition plus reranking would raise evidence recall over the baseline and, through better
grounded drafts, raise the simulated reply rate by at least three points. The test split was touched once, at the end.

## The result that looked like a win

The rule picked decomposition plus reranking over structured chunks. On the held-out split, Recall@5 went from 0.922
to 0.955 and nDCG@10 from 0.928 to 0.957. A respectable, unexciting improvement.

Then I ran both pipelines end to end through the whole bid graph, on the same jobs, and scored the drafts with the
simulator. The simulated reply rate went from 28.3% to 35.4%. The judge score went up too.

Seven points of reply rate from three points of recall should have made me suspicious immediately. It did not,
because it confirmed my hypothesis. I almost wrote "better retrieval, more replies" in the report and moved on.

## Pairing the drafts

What stopped me was a second question the assignment insisted on: where did better retrieval *not* translate into
replies, and why? To answer it I paired the two runs proposal by proposal and asked a very simple question: did the
better retriever change which project the proposal leads with?

It did for 5 proposals out of 111.

For the other 106, both pipelines found the same lead project. The naive baseline was already ranking the right
project first almost every time; my portfolio corpus is small and the job posts name their skills plainly. And yet
the reply probability on those *unchanged* proposals rose by 6.6 points.

So the improvement was not coming from finding better evidence. It was coming from what the Writer could *do* with
the same evidence.

## Chunk boundaries decide what you can quote

The difference between the two pipelines that nDCG does not see is the shape of the chunk. The naive baseline cuts
documents every 512 tokens. My shipped pipeline chunks case studies by structure, keeping "The problem", "What I did"
and "Result" together.

A case study's most persuasive line is its result: "Caught 14 regressions before release in three months." With fixed
chunks, the retriever returned the right case study, scored as a hit by every metric, but the chunk often stopped
before the "Result" section. The Writer, told to lead with a measurable outcome from the evidence and never to
invent one, had nothing to quote, so it fell back to a sentence about the project instead of its outcome.

I counted: drafts that quote a specific metric went from 8.1% with the naive baseline to 65.8% with structured
chunks. The simulated clients reward specific numbers, and the reply rate followed.

Retrieval metrics are computed at the level of "did you return a chunk from the right project". They are blind to
"did you return the *part* of the project the downstream agent needs". For a writer, those are different questions.

## The ablation agreed, once I knew how to read it

The ablation table had been telling me this all along and I had misread it. Switching off structured chunking cost
less than 0.01 nDCG@5, which I had filed as "chunking barely matters". Switching off requirement decomposition cost
0.063, which I filed as "decomposition is the important part". For retrieval, that is true. For replies, the ordering
is reversed: decomposition changes which project leads in a few cases, while chunking changes what every draft can say.

Two other results fit the same picture. Outcome boosting, preferring evidence from proposals that won, *lowered*
nDCG by 0.023. And multi-vector indexing, which stores summaries, READMEs, code and proposals separately and fuses
them, was by far the worst variant. Both were designed to be clever about *which* document to return. Neither did
anything about *what span* the writer gets.

## The uncomfortable side effect

There is a cost. With structured chunks the Writer has more quotable material and attempts more claims: unsupported
claims per proposal *before* verification went from 0.27 to 0.32. A better retriever made the writer bolder, not
more careful. After the claim verifier, both are at zero on the test split, but only because the verifier exists. If
I had shipped the better retriever without it, I would have shipped more overclaiming proposals and higher retrieval
scores at the same time.

## What I would tell someone building RAG for an agent

**Measure retrieval by what the next agent produces, not only by what the retriever returns.** I now keep two tables:
retrieval metrics on the tune split to choose candidates, and an end-to-end table (claims, judge score, simulated
reply rate, latency, cost) for the two or three that survive. The second table changed my understanding even though
it did not change the winner.

**Pair your comparisons.** Averages told me "variant B is better". Pairing the same jobs told me *why*, and the why
was not the variant's headline feature.

**Treat chunking as a product decision.** Chunk boundaries decide what a downstream writer can cite. That is closer
to "what can this agent say" than to an indexing detail.

**Put a verifier behind any retrieval improvement.** Better evidence invites more claims.

## Limits

This is one project with honest caveats. The data and the marketplace simulator are synthetic, written by me
while the official starter kit was unavailable, so the simulated clients reward what I believed clients reward:
skill coverage, specific numbers, a question, a sensible price. The runs used deterministic heuristic agents instead
of LLMs because the environment had no model access, so an LLM writer might paraphrase around a missing "Result"
section better than my heuristic writer does. The effect I measured is about the *interface* between retriever and
writer, which an LLM shares, but the size of it will change. All numbers here come from files in the repository's
`evals/results/` folder, and the runs that need real models are one command away.

The one result I am confident will survive is the method: when a retrieval improvement shows up downstream, pair the
outputs and ask what actually changed. Mine was not what I had hypothesised, and it was more useful.
