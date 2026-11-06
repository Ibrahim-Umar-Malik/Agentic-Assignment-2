"""R6 / R&D Question B: compare RAG variants on the dev set and pick the shipped pipeline by measurement.

Gold = the portfolio projects that genuinely evidence each job (evals/datasets/dev_*.jsonl `_gold.evidence`).
Metrics: Recall@5 and nDCG@5 over projects, MRR, "no-evidence honesty" (for off-domain jobs, the share where the
pipeline returns no confident evidence) and latency. Variants are compared on the TUNE split; the chosen pipeline
is then reported once on the TEST split.

    python -m evals.runners.rag_eval            # all variants, all personas
    python -m evals.runners.rag_eval --quick    # 40 jobs per persona
"""

from __future__ import annotations

import argparse
import time

from rag.retriever import get_index
from rag.variants import VARIANTS, options_for

from .common import (
    PERSONAS,
    bootstrap_ci,
    load_dev,
    mean,
    mrr,
    ndcg_at,
    pctile,
    public_job,
    recall_at,
    run_meta,
    split,
    write_result,
)

COMBOS = ["v2_hybrid_v1_decompose", "v3_rerank_v1_decompose", "v2_hybrid_v1_decompose_v4_outcome",
          "v2_hybrid_v1_decompose_v3_rerank_v4_outcome", "v6_contextual_v2_hybrid_v1_decompose_v4_outcome",
          "v8_corrective_v2_hybrid_v1_decompose_v4_outcome"]


def score_variant(spec: str, part: str, limit: int | None = None) -> dict:
    opts = options_for(spec)
    per_persona, all_r5, all_mrr, all_ndcg, lat, honest = {}, [], [], [], [], []
    for persona in PERSONAS:
        idx = get_index(persona)
        rows = split(load_dev(persona), part)
        rows = rows[:limit] if limit else rows
        r5s, mrrs, ndcgs = [], [], []
        for row in rows:
            gold = row["_gold"].get("evidence") or []
            t = time.perf_counter()
            res = idx.retrieve(public_job(row), opts)
            lat.append(time.perf_counter() - t)
            ranked = res.projects()
            if not gold:
                if row["_gold"].get("off_domain"):
                    # honest = nothing confident is offered as evidence for a job outside the portfolio
                    honest.append(1.0 if (opts.corrective and len(res.unsupported) >= max(1, len(res.requirements) // 2))
                                  or not ranked else 0.0)
                continue
            r5s.append(recall_at(ranked, gold, 5))
            mrrs.append(mrr(ranked, gold))
            ndcgs.append(ndcg_at(ranked, gold, 5))
        per_persona[persona] = {"n": len(r5s), "recall@5": mean(r5s), "mrr": mean(mrrs), "ndcg@5": mean(ndcgs)}
        all_r5 += r5s
        all_mrr += mrrs
        all_ndcg += ndcgs
    return {"variant": spec, "split": part, "n": len(all_r5), "recall@5": mean(all_r5), "recall@5_ci95": bootstrap_ci(all_r5),
            "mrr": mean(all_mrr), "ndcg@5": mean(all_ndcg), "off_domain_honesty": mean(honest),
            "latency_ms_p50": round(1000 * (pctile(lat, 50) or 0), 2), "latency_ms_p95": round(1000 * (pctile(lat, 95) or 0), 2),
            "per_persona": per_persona}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    limit = 40 if a.quick else None
    rows = []
    for spec in VARIANTS + COMBOS:
        r = score_variant(spec, "tune", limit)
        print(f"{spec:55s} R@5 {r['recall@5']:.3f}  MRR {r['mrr']:.3f}  nDCG {r['ndcg@5']:.3f}  p95 {r['latency_ms_p95']}ms")
        rows.append(r)
    # selection rule (declared before looking at test): best nDCG@5 on tune; ties (<0.005) -> lower p95 latency
    best = max(rows, key=lambda r: (round(r["ndcg@5"], 2), r["mrr"], -r["latency_ms_p95"]))
    baseline_test = score_variant("v0_naive", "test", limit)
    chosen_test = score_variant(best["variant"], "test", limit)
    write_result("rag", {"meta": run_meta(selection_rule="max nDCG@5 on tune split (2 dp), then MRR, then lower p95 latency"),
                         "tune": rows, "chosen": best["variant"], "test": {"baseline_v0": baseline_test, "chosen": chosen_test}})
    print("chosen:", best["variant"], "test nDCG@5", chosen_test["ndcg@5"], "vs naive", baseline_test["ndcg@5"])


if __name__ == "__main__":
    main()
