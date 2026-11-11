"""Risk patterns measured on REAL text (no synthetic overlays).

1. Flag rate on 5,000 real Upwork posts (data/real/jobs_sample.jsonl), for the old (v2) and current patterns.
   These posts are mostly legitimate, so a high flag rate means false alarms on real work.
2. External benchmark: "Fake-Job-Posting-Detection" (Kaggle adityammantri/trial-1, labelled real/fraudulent).
   Its licence is Unknown, so the data is NOT in this repository: run `python -m data_pipeline.prepare` first
   (kagglehub caches it) or pass --fraud PATH. The text there is lower-cased with punctuation stripped, and the
   jobs are general employment ads, so it is a hard out-of-domain test for the rule-based detector.
   A TF-IDF + logistic-regression baseline trained on the benchmark's own 70% tune split shows what a learned
   detector would add (reported only; no model trained on unknown-licence data is shipped).

    python -m evals.runners.risk_real [--fraud PATH_TO_processed_labeled_dataset_without_encoding.xlsx]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import yaml

from evals.runners.common import ROOT, bootstrap_ci, run_meta, write_result

CURRENT = ROOT / "agent" / "risk_patterns.yaml"


def load_patterns(text: str) -> list[dict]:
    return [p for p in yaml.safe_load(text)["scam"] if p["severity"] >= 0.75]


def v2_patterns() -> list[dict] | None:
    try:
        raw = subprocess.run(["git", "show", "9ba9cd9:agent/risk_patterns.yaml"], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout
        return load_patterns(raw)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def flagged(text: str, pats: list[dict]) -> bool:
    return any(re.search(p["pattern"], text) for p in pats)


def real_posts(pats_by_version: dict[str, list[dict]]) -> dict:
    rows = [json.loads(line) for line in (ROOT / "data" / "real" / "jobs_sample.jsonl").read_text().splitlines()]
    out = {"n": len(rows)}
    for v, pats in pats_by_version.items():
        hits = [r for r in rows if flagged(r["title"] + "\n" + r["description"], pats)]
        out[v] = {"flag_rate": round(len(hits) / len(rows), 4), "flagged": len(hits),
                  "examples": [h["title"][:80] for h in hits[:8]]}
    return out


def fraud_path(arg: str | None) -> Path | None:
    if arg:
        return Path(arg)
    try:
        import kagglehub

        return Path(kagglehub.dataset_download("adityammantri/trial-1")) / "processed_labeled_dataset_without_encoding.xlsx"
    except Exception:  # noqa: BLE001 - offline or not installed: the benchmark is reported as not run
        return None


def prf(y: list[int], p: list[int]) -> dict:
    tp = sum(a and b for a, b in zip(y, p, strict=True))
    fp = sum((not a) and b for a, b in zip(y, p, strict=True))
    fn = sum(a and not b for a, b in zip(y, p, strict=True))
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
            "recall_ci95": bootstrap_ci([float(b) for a, b in zip(y, p, strict=True) if a])}


def benchmark(path: Path, pats_by_version: dict[str, list[dict]], n: int = 4000) -> dict:
    import pandas as pd

    df = pd.read_excel(path)
    df = df[df["fraudulent"].isin([0, 1])].dropna(subset=["text"])
    df = pd.concat([df[df.fraudulent == 1].sample(n // 2, random_state=4016),
                    df[df.fraudulent == 0].sample(n // 2, random_state=4016)]).sample(frac=1, random_state=4016)
    df = df.reset_index(drop=True)
    tune, test = df[df.index % 10 < 7], df[df.index % 10 >= 7]
    y = test["fraudulent"].astype(int).tolist()
    out: dict = {"source": "kaggle adityammantri/trial-1 (licence Unknown; not redistributed)", "n_test": len(test),
                 "balance": "stratified 50/50 sample", "rules": {}}
    for v, pats in pats_by_version.items():
        out["rules"][v] = prf(y, [int(flagged(t, pats)) for t in test["text"]])
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    vec = TfidfVectorizer(min_df=3, ngram_range=(1, 2), max_features=50000)
    clf = LogisticRegression(max_iter=2000, C=4.0)
    clf.fit(vec.fit_transform(tune["text"]), tune["fraudulent"].astype(int))
    pred = clf.predict(vec.transform(test["text"])).tolist()
    out["tfidf_logreg_trained_on_tune"] = prf(y, pred)
    names = vec.get_feature_names_out()
    top = clf.coef_[0].argsort()[-15:][::-1]
    out["top_fraud_terms"] = [str(names[i]) for i in top]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fraud", default=None)
    a = ap.parse_args()
    pats = {"v3_current": load_patterns(CURRENT.read_text())}
    old = v2_patterns()
    if old:
        pats = {"v2_before": old, **pats}
    payload = {"meta": run_meta(split="real posts + external benchmark test split"), "real_posts": real_posts(pats)}
    fp = fraud_path(a.fraud)
    payload["fraud_benchmark"] = benchmark(fp, pats) if fp and fp.exists() else {"status": "not_run",
                                                                                 "why": "dataset not available offline"}
    write_result("risk_real", payload)
    print(json.dumps({k: v for k, v in payload.items() if k != "meta"}, indent=1)[:3000])


if __name__ == "__main__":
    main()
