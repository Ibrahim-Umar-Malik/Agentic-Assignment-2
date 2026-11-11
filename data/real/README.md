# Real data derived from public Kaggle datasets

Built by `python -m data_pipeline.prepare` (deterministic, seed 4016). The raw CSVs are **not** committed. They
are downloaded and cached by `kagglehub` (`pip install -e .[data]`), and every derived file here can be rebuilt
from them.

| File | What | From |
|---|---|---|
| `jobs_sample.jsonl` | 5,000 cleaned job posts: title, description, skill tags, budget or hourly range, Connects, experience level, client signals, our category | [A] |
| `market_stats.json` | paid hourly rates and fixed-price totals (p10–p90) by category from 300k contracts, plus 2024 posted budgets | [C], [U], [T] |
| `summary.json` | pipeline counts, persona floors, dev-set composition | all |

The dev sets (`evals/datasets/dev_*.jsonl`), GigSim's live jobs, clients and price history
(`data/gigsim_seed/`) are built from the same sources. Each record says which fields are real and which are
synthetic in `_provenance`.

## Attribution and licences

| Key | Dataset | Author | Licence | How it is used |
|---|---|---|---|---|
| A | [Upwork freelance jobs (+60k)](https://www.kaggle.com/datasets/ahmedmyalo/upwork-freelance-jobs-60k) | ahmedmyalo | Apache 2.0 | job posts, skill tags, budgets, Connects, client signals (redistributed in cleaned form) |
| U | [Upwork Job Postings Dataset 2024 (50K Records)](https://www.kaggle.com/datasets/asaniczka/upwork-job-postings-dataset-2024-50k-records) | asaniczka | ODC-By 1.0 | posted budgets and hourly ranges (aggregates only) |
| T | [All Upwork Job Postings, Monthly Tracker (200k+)](https://www.kaggle.com/datasets/asaniczka/all-jobs-on-upwork-200k-plus) | asaniczka | ODC-By 1.0 | posted budgets and hourly ranges (aggregates only) |
| C | [Freelance Contracts Dataset (1.3 Million Entries)](https://www.kaggle.com/datasets/asaniczka/freelance-contracts-dataset-1-3-million-entries) | asaniczka | ODC-By 1.0 | paid rates and totals: market statistics, GigSim price history, persona floors |
| S | [Freelancer Marketplace Dataset for ML & Analytics](https://www.kaggle.com/datasets/sarveshchhetri/freelancer-success-earnings-and-churn-prediction) | sarveshchhetri | Apache 2.0 | persona job-success and response-time defaults only. The dataset is itself synthetic ("real-world style"), so it was rejected for pricing |
| F | [Fake-Job-Posting-Detection](https://www.kaggle.com/datasets/adityammantri/trial-1) | adityammantri | Unknown | external benchmark for the Risk agent. Used locally only; nothing from it is redistributed |

ODC-By requires attribution, which this table provides. The job posts are public marketplace listings
collected by the dataset authors. Before anything was committed, the pipeline replaced email addresses, phone
numbers and links in descriptions with placeholders.
