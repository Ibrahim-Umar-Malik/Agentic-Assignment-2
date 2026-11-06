from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select

from core import config
from core.db import approvals, engine, jobs, pipeline, row_dict, runs

from ..auth.users import current_user

router = APIRouter(prefix="/api", tags=["analytics"])


def _pct(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    vals = sorted(vals)
    return round(vals[min(len(vals) - 1, int(p * len(vals)))], 3)


@router.get("/analytics")
def analytics(user: dict = Depends(current_user)) -> dict:
    uid = user["id"]
    with engine().begin() as c:
        pl = [row_dict(r) for r in c.execute(select(pipeline).where(pipeline.c.user_id == uid))]
        rr = [row_dict(r) for r in c.execute(select(runs).where(runs.c.user_id == uid))]
        jj = [row_dict(r) for r in c.execute(select(jobs).where(jobs.c.user_id == uid))]
        rej = [row_dict(r) for r in c.execute(select(approvals).where(approvals.c.user_id == uid, approvals.c.status.in_(["completed", "decided", "resumed"])))]
    by_cat: dict[str, Counter] = defaultdict(Counter)
    for p in pl:
        by_cat[p.get("category") or "unknown"]["sent"] += 1
        if p["stage"] in ("replied", "interview", "hired"):
            by_cat[p.get("category") or "unknown"]["replied"] += 1
        if p["stage"] == "hired":
            by_cat[p.get("category") or "unknown"]["hired"] += 1
    cats = [{"category": k, "sent": v["sent"], "reply_rate": round(v["replied"] / v["sent"], 3) if v["sent"] else 0,
             "hire_rate": round(v["hired"] / v["sent"], 3) if v["sent"] else 0} for k, v in by_cat.items()]
    connects_spent = sum(p.get("connects") or 0 for p in pl)
    replied = sum(1 for p in pl if p["stage"] in ("replied", "interview", "hired"))
    bid_runs = [r for r in rr if r["graph"] == "bid" and r.get("finished_at")]
    lat = [r["finished_at"] - r["started_at"] for r in bid_runs]
    reasons = Counter((r.get("decision") or {}).get("reason", "").strip().lower() for r in rej if (r.get("decision") or {}).get("action") == "reject")
    skip_reasons = Counter((j.get("summary") or {}).get("reason", "").split(";")[0][:60] for j in jj if j["status"] == "skipped")
    return {
        "funnel": {"seen": len(jj), "analysed": sum(1 for j in jj if j.get("thread_id")), "recommended_bid": sum(1 for j in jj if j.get("action") == "bid"),
                   "submitted": len(pl), "replied": replied, "hired": sum(1 for p in pl if p["stage"] == "hired")},
        "by_category": cats,
        "connects": {"spent": connects_spent, "per_reply": round(connects_spent / replied, 2) if replied else None,
                     "weekly_budget": (user.get("settings") or {}).get("weekly_connects_budget")},
        "cost_latency": {"runs": len(bid_runs), "p50_latency_s": _pct(lat, 0.5), "p95_latency_s": _pct(lat, 0.95),
                         "usd_total": round(sum(r.get("cost_usd") or 0 for r in rr), 4),
                         "usd_per_run": round(sum(r.get("cost_usd") or 0 for r in rr) / len(rr), 5) if rr else None,
                         "declared": config.get("budgets.declared")},
        "top_rejection_reasons": [{"reason": k, "count": v} for k, v in reasons.most_common(5) if k],
        "top_skip_reasons": [{"reason": k, "count": v} for k, v in skip_reasons.most_common(5) if k],
    }


@router.get("/pipeline")
def board(user: dict = Depends(current_user)) -> dict:
    with engine().begin() as c:
        rows = [row_dict(r) for r in c.execute(select(pipeline).where(pipeline.c.user_id == user["id"]))]
        drafted = [row_dict(r) for r in c.execute(select(approvals).where(approvals.c.user_id == user["id"], approvals.c.kind == "proposal",
                                                                         approvals.c.status == "pending"))]
    stages = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"]
    cols = {s: [] for s in stages}
    for a in drafted:
        cols["drafted"].append({"job_id": a["job_id"], "title": a["payload"].get("job", {}).get("title"), "stage": "drafted",
                                "bid": (a["payload"].get("price") or {}).get("amount"), "approval_id": a["id"]})
    for r in rows:
        cols.setdefault(r["stage"], []).append(r)
    return {"stages": stages, "columns": cols}
