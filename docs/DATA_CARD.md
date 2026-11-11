# Data card

GigBid's data is a mix of **real public data** (job posts, client signals, market prices) and **synthetic data**
where no public data exists (freelancer portfolios, client reply behaviour, adversarial test cases). Every
record carries a `_provenance` field that says which of its fields are real and which are synthetic.

## Sources

| Key | Dataset (Kaggle) | Licence | Rows used | Used for |
|---|---|---|---|---|
| A | ahmedmyalo/upwork-freelance-jobs-60k (2023) | Apache 2.0 | 63,950 raw, 36,265 after cleaning | **job posts** (title, description, Upwork skill tags, budget/hourly range, Connects, experience level) and **client signals** (payment verified, total spent, rating, reviews, country, applicants) |
| U | asaniczka/upwork-job-postings-dataset-2024-50k-records | ODC-By 1.0 | 53,058 | posted budgets / hourly ranges by category (`market_stats.json`) |
| T | asaniczka/all-jobs-on-upwork-200k-plus | ODC-By 1.0 | ~244k (3 files) | same, combined with U (250k-row sample) |
| C | asaniczka/freelance-contracts-dataset-1-3-million-entries | ODC-By 1.0 | 1,292,791 (300k sample) | **paid** hourly rates and fixed-price totals: GigSim's price history, `market_stats.json`, persona hourly floors |
| S | sarveshchhetri/freelancer-success-earnings-and-churn-prediction | Apache 2.0 | 12,000 | persona job-success and response-time defaults only |
| F | adityammantri/trial-1 ("Fake-Job-Posting-Detection") | Unknown | 54,391 (4,000 stratified) | external benchmark for the Risk agent (`evals/results/risk_real.json`); used locally, not redistributed |

Attribution, links and the per-file breakdown are in `data/real/README.md`.

### Why these, and what was rejected

* **A is the backbone** because it is the only dataset with the full job (description *and* skill tags *and*
  Connects *and* client history). U and T have descriptions or budgets but no skills or clients, so they are
  used for price statistics only.
* **C gives what clients actually paid**, not what they posted. The persona floors (ai_ml $30/h, fullstack
  $21/h, data_analyst $30/h) are the median paid hourly rate in each persona's categories. Before this rebuild
  they were $40–45/h, values I had made up.
* **S was evaluated and mostly rejected.** Its median hourly rate is exactly $280 for every skill, which is not
  plausible market data, and its own description says "real-world style", meaning synthetic. It sets only two
  cosmetic profile fields.
* **F is out of domain** (general employment ads, lower-cased, punctuation stripped). Its fraud class looks
  templated ("earn 5000week immediate hiring contact now"). That makes it a useful *stress test* for the scam
  rules, but not an estimate of real-world recall.

## Preprocessing (`data_pipeline/prepare.py`, deterministic, seed 4016)

1. **Clean.** HTML unescape; replace emails, phone numbers and URLs with placeholders (PII scrub before
   anything is committed); collapse whitespace.
2. **Deduplicate** on the Upwork job id in the URL, then on title + first 200 characters: 63,950 → 59,594.
3. **Filter** to English (more than 97% ASCII), descriptions of 150–6,000 characters → 49,912, and posts with a
   usable budget or hourly range → 36,265.
4. **Categorise** each post into one of GigBid's 13 categories, or "other", with a transparent keyword scorer
   over title, tags and description (`data_pipeline/categories.py`). Title or tag hits count double, and a
   single passing mention in the description is not enough. Resulting mix: other 46%, frontend 25%,
   fullstack 6.5%, mobile 6%, ecommerce 5%, classic ML 2.6%, analytics 2%, spreadsheet 1.9%, BI 1.5%,
   devops 1.5%, LLM apps 1.3%, data engineering 0.5%, computer vision 0.2%.
5. **Market statistics** per category from C (paid) and U+T (posted): `data/real/market_stats.json`. Example:
   LLM-app work is paid a median of $30/h and $250 per fixed contract; spreadsheet work $20/h and $60.
6. **Label** (silver labels, below), **sample** dev sets and GigSim's live stream, and **build clients** from
   the real client signals of each post.

<!-- table:data -->
| Data pipeline (data_pipeline/prepare.py) | Count |
|---|---|
| Upwork job posts (dataset A), raw | 63,950 |
| after de-duplication | 59,594 |
| after English / length filter | 49,912 |
| with a usable budget (the job pool) | 36,265 |
| Contracts used for paid-rate statistics (dataset C sample) | 300,000 of 1,292,791 |
| Persona hourly floors from real paid rates (ai_ml / fullstack / data_analyst) | $30 / $21 / $30 |
| Dev-set jobs (3 personas × 200), GigSim live jobs | 600, 180 |
<!-- /table:data -->

## Dev sets (`evals/datasets/dev_{persona}.jsonl`, 200 jobs each)

Sampling (stratified so that both classes are measurable): 10% scam overlays, 10% injection overlays, 6%
reposts, 22% off-domain posts (other personas' categories or "other"), and the rest in-domain. Of the in-domain
draws, 55% come from fit-labelled posts. Scam and injection overlays go on fit posts, because that is where
they do harm. The live GigSim stream (60 per persona) is drawn from disjoint posts.

| Kind | ai_ml | fullstack | data_analyst | Source |
|---|---|---|---|---|
| fit | 67 | 60 | 64 | real post, silver label |
| weak fit (in-domain, skills not covered) | 22 | 36 | 28 | real post, silver label |
| off-domain | 46 | 45 | 51 | real post |
| lowball (budget below market) | 6 | 19 | 11 | real post, real budget |
| scam | 31 | 18 | 23 | real post + **synthetic** scam text, real brand-new ($0 spent) client |
| injection | 19 | 14 | 12 | real post + **synthetic** prompt injection |
| repost | 9 | 8 | 11 | **synthetic** repost of an earlier post |

Splits are by row index: **70% tune** (variants, thresholds and every fix in report section 8 were chosen on
it), and **30% test** (reported). No choice was made on test.

### Silver labels (`label_job` in `data_pipeline/prepare.py`)

The datasets say nothing about whether *these* freelancers should bid, so labels come from written rules:

* **Evidence:** persona projects that share a canonical skill named in the post's title or tags (plus the
  post's category, or a second shared skill), or that share three skills anywhere in the post.
* **Fit:** the category belongs to the persona; at least 60% of the post's non-neutral Upwork skill tags are
  tags the persona can **prove** from portfolio text (`data_pipeline/tag_competence.py`), with at least 2 such
  tags; and at least one evidence project exists.
* **Lowball:** an hourly maximum below 60% of the persona floor, or a fixed budget below the category's paid p25.
* **Bid** = fit, and payment verified, and not lowball, and not a scam. Injection overlays keep the label of the
  post underneath.
* **Fair price band:** the client's own posted hourly range, or 75–100% of a fixed budget. When the post has
  neither, the category's paid IQR is used.

A 45-row audit sheet (`evals/datasets/label_audit.csv`, 15 per persona) has blank `human_kind` / `human_bid`
columns for a human check of these rules.

## Synthetic parts (and why)

| Part | Why synthetic | Where |
|---|---|---|
| Three freelancer portfolios (CVs, 16 case studies, 11 repos with code, reviews, 50 past proposals each) | No public dataset has portfolios with case studies, code and past proposals with outcomes | `data/personas/`, `scripts/generate_standin_data.py` |
| Client reply behaviour (`_hidden` preferences in GigSim) | No public dataset links proposals to replies | `data/gigsim_seed/clients.json` |
| Scam text, prompt injections, reposts | Needed as known ground truth for safety metrics | overlays on real posts, flagged in `_provenance.overlay` |
| Screening questions, posting times | Not in the datasets | `_provenance.synthetic` |
| Conversations (client replies) | Generated by GigSim from the hidden preferences | `gigsim_standin/sim.py` |

GigSim client **responsiveness is calibrated on real competition**: posts with more applicants (from A's
`Applicants_Num`) get less responsive clients.

## Scam rules measured on real text

<!-- table:risk_real -->
| Scam rules on real text | v2 (before) | v3 (shipped) |
|---|---|---|
| Scam-level flags on 5,000 real Upwork posts | 2.9% | 0.4% |
| External fake-job benchmark: recall (n=1200, 50% fraud) | 0.0% | 80.7% |
| External fake-job benchmark: precision | 0.0% | 99.8% |

A TF-IDF + logistic-regression detector trained on the benchmark's own tune split reaches precision 99.5% / recall 93.4%; its top features (earn, no, immediate, hiring, knowledge in) show the fraud class is templated, so this is an upper bound for that dataset, not for Upwork.
<!-- /table:risk_real -->

## Known limitations and threats to validity

* **Silver labels share logic with the system.** Both the labels and the Fit Matcher reason from skill evidence
  in the portfolio, so agreement is partly by construction. The labels use the client's Upwork tags and
  lexical evidence in the portfolio text; the matcher uses retrieval through the Portfolio MCP server. The
  audit sheet exists to measure this.
* **Simulated replies are still circular:** I wrote GigSim's reply model, so reply-rate results show that GigBid
  optimises what the simulator rewards. The real-data rebuild did not change this.
* **Time and platform drift:** A is from 2023 and U/T/C from 2024. Connects prices and the fee structure have
  changed since.
* **Selection bias:** A was scraped by search keyword (Developer, Marketing, Data science, 3D), so writing,
  admin and design jobs are under-represented.
* **Categorisation is keyword-based**, so some posts land in the wrong category (for example, lead-generation
  posts that mention "data"). This is visible in the off-domain and weak-fit rows.
* Offline retrieval uses a hash embedder, so numbers will change with the open-weight embedder.

## Regenerating

```bash
uv pip install -e ".[data]"   # kagglehub, pandas, openpyxl, scikit-learn
make data                     # personas + policy, then Kaggle -> data/real, data/gigsim_seed, evals/datasets
make eval                     # evals/results/*.json and the tables in README / report / write-up
```
