# Signature extension: X2 Proposal experiments

## What it does

GigBid runs a live A/B test on how proposals are written and tells the freelancer, with a significance test,
whether one strategy gets more replies.

* **Experiment** (`agent/config.yaml: experiments.opening`): *question* arm = the cover letter asks the client
  one specific clarifying question about their project; *statement* arm = no question, it closes with a concrete
  next step instead. Everything else (evidence, price, length) is identical.
* **Assignment** (`agent/experiments.py: assign`): when the decision node says "bid", the job gets an arm from a
  stable hash of (user, experiment id, job id). It is stored in the checkpointed state, so a crash-and-resume or
  a regeneration never flips the arm.
* **Writer**: the heuristic writer and the LLM prompt both honour the arm; the arm is shown on the run trace.
* **Measurement** (`agent/experiments.py: summarize`, served in `/api/analytics` → `experiment`): proposals
  that reached a final-enough stage are counted per arm; a two-sided two-proportion z-test gives the lift, a
  95% CI and a p-value. A winner is only declared once both arms have 30 proposals and p < 0.05; it is then
  offered to the user, never applied silently.

## How it was evaluated

`evals/runners/gigsim_outcomes.py` writes every proposal GigBid bids on in **both** arms (paired design: same
job, same evidence, same price) and scores each with the GigSim client model, then simulates the live
randomised experiment to estimate how many proposals per arm the z-test needs.

<!-- table:ab -->
| X2 experiment: ask one clarifying question vs close with a next step | Value |
|---|---|
| Jobs (paired, both arms written) | 111 |
| Reply probability: statement / question | 26.4% / 35.7% |
| Paired lift (question − statement) | +9.3 points (95% CI [7.8, 11.1]) |
| Chance the live z-test calls it at 30 / 120 / 500 proposals per arm | 10.0% / 36.0% / 88.5% |
<!-- /table:ab -->

## What it showed

The question arm gets more replies on every persona in the simulator, because a share of clients reward a
specific question. But the effect is small relative to reply-rate noise: with a realistic freelancer volume
(10–20 proposals a week) the live test needs months before it can call a winner. That is the honest product
lesson: the feature is most useful as a slow, safe default-setter (or pooled across many freelancers), not as a
weekly dashboard. The circularity caveat in `DATA_CARD.md` applies: the GigSim stand-in's client model was
written by the same author.
