"""Render every results table used in README.md and the R&D report from evals/results/*.json.

    python -m evals.make_tables            # rewrite the marked blocks in README.md and docs/report/report.md
    python -m evals.make_tables --check    # CI: fail if a marked block differs from what the JSON says

A block is delimited by <!-- table:NAME --> ... <!-- /table:NAME -->. Numbers are never typed by hand."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "evals" / "results"
TARGETS = [ROOT / "README.md", ROOT / "docs" / "report" / "report.md", ROOT / "docs" / "writeup.md", ROOT / "docs" / "EXTENSION.md"]


def load(name: str) -> dict:
    p = RES / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def f(v, nd=3, pct=False):
    if v is None:
        return "n/a"
    if isinstance(v, dict):
        return "not run"
    return f"{100 * v:.1f}%" if pct else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def md(head: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def t_rag() -> str:
    d = load("rag")
    if not d:
        return "_run `make eval` to produce evals/results/rag.json_"
    rows = [[("**" + r["variant"] + "**") if r["variant"] == d["chosen"] else r["variant"], f(r["recall@5"]), f(r["mrr"]),
             f(r["ndcg@5"]), f(r["latency_ms_p95"], 1)] for r in d["tune"]]
    t = d["test"]
    foot = (f"\n\nChosen by rule ({d['meta']['selection_rule']}): **{d['chosen']}**. Held-out test split: nDCG@5 "
            f"{f(t['chosen']['ndcg@5'])} vs naive {f(t['baseline_v0']['ndcg@5'])}; Recall@5 {f(t['chosen']['recall@5'])} "
            f"(95% CI {t['chosen']['recall@5_ci95']}) vs {f(t['baseline_v0']['recall@5'])}. Embedder `{d['meta']['embedder']}`, "
            f"reranker `{d['meta']['reranker']}`, commit `{d['meta']['commit']}`.")
    return md(["Variant (tune split)", "Recall@5", "MRR", "nDCG@5", "p95 ms"], rows) + foot


def t_ablation() -> str:
    d = load("ablation")
    if not d:
        return "_n/a_"
    return md(["Setting (tune split)", "Recall@5", "nDCG@5", "Δ nDCG@5"],
              [[r["setting"], f(r["recall@5"]), f(r["ndcg@5"]), f(r.get("delta_ndcg@5"), 4) if "delta_ndcg@5" in r else "-"] for r in d["retrieval"]])


def t_decision() -> str:
    d = load("decision")
    if not d:
        return "_n/a_"
    t = d["test"]
    rows = [["Bid/skip accuracy", f(t["decision"]["accuracy"], pct=True) + f" (95% CI {[round(100 * x, 1) for x in t['decision']['accuracy_ci95']]})"],
            ["Bid precision / recall / F1", f"{f(t['decision']['bid_precision'])} / {f(t['decision']['bid_recall'])} / {f(t['decision']['bid_f1'])}"],
            ["Scam posts not bid on", f"{f(t['scam']['recall'], pct=True)} of {t['scam']['n']}"],
            ["Injected posts flagged / obeyed", f"{f(t['injection']['flagged'], pct=True)} flagged, {t['injection']['obeyed']} of {t['injection']['n']} obeyed"],
            ["Unsupported claims without verifier → shipped", f"{f(t['grounding']['unsupported_rate_without_verifier'], pct=True)} → {f(t['grounding']['unsupported_rate_shipped'], pct=True)} ({t['grounding']['claims']} claims)"],
            ["Bids inside the fair price band", f"{f(t['price']['in_fair_band'], pct=True)} of {t['price']['n']}"],
            ["Latency per job p50 / p95", f"{f(t['cost_latency']['p50_latency_s'], 2)}s / {f(t['cost_latency']['p95_latency_s'], 2)}s"],
            ["Errors", f"{t['errors']} of {t['n']}"]]
    sw = d.get("threshold_sweep", {})
    return (md([f"Metric (test split, n={t['n']}, profile `{d['meta']['profile']}`)", "Value"], rows) +
            f"\n\nThresholds chosen on the tune split by F1: bid_min_fit={sw.get('bid_min_fit')}, max_risk={sw.get('max_risk')} (tune F1 {sw.get('f1_on_tune')}).")


def t_outcomes() -> str:
    d = load("gigsim_outcomes")
    if not d:
        return "_n/a_"
    names = {"gigbid": "**GigBid**", "template_all": "Template, bid on all", "reuse_best_past": "Reuse best past proposal"}
    rows = [[names[k], v["bids"], v["connects"], f(v["reply_rate"], pct=True), f(v["replies_per_100_connects"], 2),
             f(v["expected_interviews"], 1), f(v["expected_hires"], 1), v["scam_bids"]] for k, v in d["systems"].items()]
    return md(["System (180 test jobs)", "Bids", "Connects", "Reply rate", "Replies / 100 Connects", "Interviews", "Hires", "Scam bids"], rows)


def t_ab() -> str:
    d = load("gigsim_outcomes").get("ab_experiment")
    if not d:
        return "_n/a_"
    pw = d["power_by_n_per_arm"]
    return md(["X2 experiment: ask one clarifying question vs close with a next step", "Value"],
              [["Jobs (paired, both arms written)", d["n_jobs"]],
               ["Reply probability: statement / question", f"{f(d['reply_prob_statement'], pct=True)} / {f(d['reply_prob_question'], pct=True)}"],
               ["Paired lift (question − statement)", f"{100 * d['paired_diff_question_minus_statement']:+.1f} points (95% CI {[round(100 * x, 1) for x in d['paired_diff_ci95']]})"],
               ["Chance the live z-test calls it at 30 / 120 / 500 proposals per arm", f"{f(pw['30'], pct=True)} / {f(pw['120'], pct=True)} / {f(pw['500'], pct=True)}"]])


def t_arch() -> str:
    d = load("architecture_compare").get("arms", {})
    if not d:
        return "_n/a_"
    rows = []
    for k in ("graph", "react", "supervisor"):
        v = d.get(k, {})
        if v.get("status") == "not_run":
            rows.append([k, "not run: needs an LLM", "", "", "", ""])
        else:
            rows.append([k, f(v.get("accuracy"), pct=True), v.get("scam_bids"), f(v.get("unsupported_claim_rate"), pct=True),
                         f(v.get("mean_tool_calls"), 1), f(v.get("p95_latency_s"), 2) + "s"])
    return md(["Architecture (50 jobs)", "Decision accuracy", "Scam bids", "Unsupported claims", "Tool calls / job", "p95 latency"], rows)


def t_tools() -> str:
    d = load("tool_granularity").get("designs", {})
    if not d:
        return "_n/a_"
    return md(["Tool design", "Tools", "Schema tokens per turn (≈)", "Min calls / task", "Selection accuracy"],
              [[k, v["tools"], v["schema_tokens_approx"], f(v["min_calls_per_task"], 2), f(v.get("selection_accuracy"), pct=True)] for k, v in d.items()])


def t_judge() -> str:
    d = load("judge_calibration")
    if not d:
        return "_n/a_"
    h = d["human"]
    hv = (f"Cohen κ {h['cohen_kappa']}, quadratic κ {h['quadratic_weighted_kappa']} (n={h['n']})" if h["status"] == "calibrated"
          else f"awaiting human labels ({h['labelled']}/30)")
    return md(["Judge calibration (30 items)", "Value"],
              [["Mean judge score: GigBid / reuse past / template", " / ".join(str(d['mean_overall_by_source'].get(k, 'n/a')) for k in ('gigbid', 'reuse_past', 'template'))],
               ["Agreement with human labels", hv],
               ["Proxy: quadratic κ vs GigSim client model (not human)", d["proxy_vs_gigsim_client_model"]["quadratic_weighted_kappa"]]])


def t_b5() -> str:
    d = load("variant_e2e").get("rows", {})
    if not d:
        return "_n/a_"
    rows = []
    for spec, v in d.items():
        name = "V0 naive" if spec == "v0_naive" else f"**Shipped: {spec}**"
        cost = f"${v['usd_per_proposal']:.4f}" if v["usd_per_proposal"] is not None else "n/a"
        rows.append([name, f(v.get("recall@5")), f(v.get("ndcg@10")),
                     f(v["unsupported_claims_per_proposal"], 2) + f" ({f(v['unsupported_claims_per_proposal_before_verify'], 2)} before verify)",
                     f(v["judge_score"], 2), f(v["gigsim_reply_rate"], pct=True), f(v["p95_latency_s"], 2), cost])
    return md(["Variant", "Evidence Recall@5", "nDCG@10", "Unsupported claims / proposal", "Judge score", "GigSim reply rate",
               "p95 latency (s)", "Cost / proposal (USD)"], rows)


def t_injection() -> str:
    on = load("decision").get("test", {}).get("injection")
    off = load("injection_no_defences").get("test", {}).get("injection")
    if not on:
        return "_n/a_"
    before = f"{off['obeyed']} of {off['n']}" if off else "not run (needs an LLM writer; the offline writer cannot follow instructions)"
    return md(["Planted-injection jobs (test split)", "Attack success"],
              [["Defences off (no sanitising, no delimiting)", before], ["Defences on (shipped)", f"{on['obeyed']} of {on['n']}"]])


TABLES = {"b5": t_b5, "injection": t_injection,"rag": t_rag, "ablation": t_ablation, "decision": t_decision, "outcomes": t_outcomes, "ab": t_ab, "arch": t_arch,
          "tools": t_tools, "judge": t_judge}


def render(text: str) -> str:
    for name, fn in TABLES.items():
        text = re.sub(rf"(<!-- table:{name} -->\n).*?(\n<!-- /table:{name} -->)", lambda m, fn=fn: m.group(1) + fn() + m.group(2), text, flags=re.S)
    return text


def main() -> int:
    check = "--check" in sys.argv
    bad = []
    for p in TARGETS:
        if not p.exists():
            continue
        old = p.read_text()
        new = render(old)
        if check and new != old:
            bad.append(str(p.relative_to(ROOT)))
        elif not check and new != old:
            p.write_text(new)
            print(f"updated {p.relative_to(ROOT)}")
    if bad:
        print("numbers differ from evals/results (run `python -m evals.make_tables`): " + ", ".join(bad))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
