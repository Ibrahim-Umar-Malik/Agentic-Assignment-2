# Data card

## What is in the repository

**Everything here is synthetic.** The official AI-4016 starter kit (GigSim, three persona corpora, dev set and
policy pack) was not available when this build was made, so `scripts/generate_standin_data.py` generates
stand-ins with the same shape, deterministically (`SEED=4016`). When the official kit is dropped in, the code
reads it from the same paths (`gigsim/`, `data/personas/`, `data/policy_pack/`, `evals/datasets/`) and every
result is regenerated with `make eval`. No real client data, no live-mode data and no tokens are committed.

| Asset | Path | Size | Notes |
|---|---|---|---|
| Personas | `data/personas/{ai_ml, fullstack, data_analyst}` | 3 freelancers (Sana Mirza, Daniel Okafor, Lena Kowalski) | each: CV, 16 case studies (Markdown with JSON front matter), 11 repos (README + code), 50 past proposals with outcomes, 7–11 client reviews |
| GigSim seed | `data/gigsim_seed/` | 320 clients (40 scam), 180 live jobs, 1,500 historical awarded jobs | clients carry hidden preferences (`_hidden`) used only by the simulator's reply model |
| Policy pack | `data/policy_pack/policy.md`, `rules.yaml` | 5 rules (P1, P2, P4, P6, P7) + P3 and MP2 enforced in code | P1 contact details (redact), P2 off-platform payment (block), P4 guarantees (rewrite), P6 free work (block), P7 length (block); P3 unsupported claims from human edits (block); MP2 policy-v2 screening answers (block) |
| Dev sets | `evals/datasets/dev_{persona}.jsonl` | 200 jobs per persona (600) | gold labels in `_gold`: bid, scam, injection type, job kind, evidence projects, fair price band, duplicate-of |
| Judge set | `evals/datasets/judge_set.jsonl`, `judge_labels.csv` | 30 proposals | blind CSV for human labelling (source column withheld) |

### Job kinds in the dev sets (per persona, approximate)

fit 52%, off-domain 18%, scam 13%, planted injection 10%, lowball 7%. Injection types: canary word, contact
exfiltration, price override, prompt leak.

### Messiness on purpose

Skills that appear only in code, not in the README (e.g. Celery); aliases (`LLM agents` vs `agentic`);
reposted duplicate jobs; vague posts; clients with unverified payment; reviews that mention a different project.

## Splits

Each dev set is split deterministically by row index: **70% tune** (choose variants and thresholds) and
**30% test** (report once). No hyper-parameter, threshold or variant was chosen on the test split
(`evals/runners/common.py: split`). The hidden test set never enters the repository.

## Known limitations and threats to validity

* **Circularity.** The same author wrote the data generator, the GigSim client model and GigBid. Reply-rate
  results therefore show that GigBid optimises what this simulator rewards (skill coverage, specific metrics,
  a question, sensible length and price), not that it would win on Upwork. The official GigSim removes this.
* Gold evidence labels are generated from the project a job was derived from, plus a related project; real
  freelancers would disagree on some.
* Text is template-generated English; there are no typos, non-English posts or images.
* Offline retrieval uses a hash embedder; numbers will change with the open-weight embedder (bge-small).

## Regenerating

```bash
make seed      # rewrites data/personas, data/gigsim_seed, evals/datasets (identical output for SEED=4016)
make eval      # rewrites evals/results/*.json and the tables in README / report
```
