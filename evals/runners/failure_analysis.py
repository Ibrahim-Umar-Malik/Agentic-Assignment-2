"""Report §8: group every failed TEST-split job from evals/results/decision.json into the assignment's taxonomy.

A failure is: a wrong bid (gold says skip), a wrong skip (gold says bid), a bid priced outside the job's fair
band, an unsupported claim left in a draft, a compliance miss, an obeyed injection, or a tool error."""

from __future__ import annotations

import json
from collections import Counter, defaultdict

from .common import RESULTS, load_dev, run_meta, write_result


def classify(r: dict) -> list[str]:
    out = []
    if r.get("error"):
        out.append("tool error")
    if r["action"] == "bid" and not r["gold_bid"]:
        out.append({"lowball": "wrong bid: lowball budget", "off_domain": "wrong bid: off-domain (missed evidence gap)",
                    "weak_fit": "wrong bid: weak fit (client's skill tags mostly not in portfolio)",
                    "duplicate": "wrong bid: repost not recognised", "scam": "wrong bid: scam"}.get(r["kind"], "wrong bid: other"))
    if r["action"] != "bid" and r["gold_bid"]:
        out.append("wrong skip: injected post treated as client risk" if r["kind"] == "injection" else "wrong skip: risk/fit threshold")
    if r["action"] == "bid" and r.get("in_band") is False:
        out.append("mispriced")
    if r.get("unsupported_after"):
        out.append("unsupported claim")
    if r.get("obeyed_injection"):
        out.append("injection obeyed")
    return out


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="decision.json", help="a decision-eval result file in evals/results/")
    ap.add_argument("--out", default="failures")
    a = ap.parse_args()
    d = json.loads((RESULTS / a.source).read_text())
    gold = {row["id"]: row for p in ("ai_ml", "fullstack", "data_analyst") for row in load_dev(p)}
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in d["rows"]:
        for c in classify(r):
            g = gold[r["id"]]
            groups[c].append({"id": r["id"], "title": g["title"], "kind": r["kind"], "fit": r["fit"], "risk": r["risk"],
                              "price": r["price"], "fair_band": g["_gold"].get("fair_band"), "budget": g.get("budget"),
                              "budget_type": g.get("budget_type")})
    counts = Counter({k: len(v) for k, v in groups.items()})
    write_result(a.out, {"meta": run_meta(source=f"evals/results/{a.source}", split="test"),
                              "counts": dict(counts.most_common()), "total_failed_jobs": len({x["id"] for v in groups.values() for x in v}),
                              "examples": {k: v[:6] for k, v in groups.items()}})
    print(counts.most_common())


if __name__ == "__main__":
    main()
