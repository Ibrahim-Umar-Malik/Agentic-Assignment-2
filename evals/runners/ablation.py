"""Ablation of the shipped retrieval pipeline: switch off one component at a time and measure the drop on the
TUNE split (so the test split stays untouched). Also ablates claim verification on generated drafts."""

from __future__ import annotations

from dataclasses import replace

from rag.retriever import get_index, shipped_options

from .common import PERSONAS, load_dev, mean, ndcg_at, public_job, recall_at, run_meta, split, write_result


def retrieval(opts) -> dict:
    r5, nd = [], []
    for persona in PERSONAS:
        idx = get_index(persona)
        for row in split(load_dev(persona), "tune"):
            gold = row["_gold"].get("evidence") or []
            if not gold:
                continue
            ranked = idx.retrieve(public_job(row), opts).projects()
            r5.append(recall_at(ranked, gold, 5))
            nd.append(ndcg_at(ranked, gold, 5))
    return {"recall@5": mean(r5), "ndcg@5": mean(nd), "n": len(nd)}


def main() -> None:
    base = shipped_options()
    full = retrieval(base)
    rows = [{"setting": "shipped (all components)", **full}]
    toggles = {"structured chunking -> fixed 512-token chunks": {"chunking": "fixed"},
               "requirement decomposition off": {"decompose": False},
               "reranking off": {"rerank": False}}
    for name, upd in toggles.items():
        r = retrieval(replace(base, **upd))
        rows.append({"setting": name, **r, "delta_ndcg@5": round(r["ndcg@5"] - full["ndcg@5"], 4)})
    # adding components the selection rule did not pick (shows they were tried, not forgotten)
    for name, upd in {"+ hybrid BM25": {"hybrid": True}, "+ contextual chunk headers": {"contextual": True},
                      "+ outcome boost": {"outcome": True}, "+ HyDE": {"hyde": True}}.items():
        r = retrieval(replace(base, **upd))
        rows.append({"setting": name, **r, "delta_ndcg@5": round(r["ndcg@5"] - full["ndcg@5"], 4)})
    for r in rows:
        print(f"{r['setting']:50s} nDCG@5 {r['ndcg@5']:.3f} {r.get('delta_ndcg@5', '')}")
    write_result("ablation", {"meta": run_meta(split="tune", shipped=str(base)), "retrieval": rows,
                              "note": "Claim-verification ablation is in decision.json (unsupported-claim rate with and without the verifier)."})


if __name__ == "__main__":
    main()
