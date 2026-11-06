"""Bid decision: skip, watch or bid, from the three parallel analyses. Thresholds live in config (decision.*)."""

from __future__ import annotations

from core import config

from ..handoffs import BidDecision
from .common import node


def decide(state: dict) -> BidDecision:
    d = config.get("decision", {})
    fit = (state.get("fit") or {}).get("fit_score", 0.0)
    risk = state.get("risk") or {}
    job = state.get("job") or {}
    floor = float((state.get("meta") or {}).get("hourly_floor") or 0)
    reasons: list[str] = []
    if (state.get("meta") or {}).get("duplicate_of"):
        return BidDecision(action="skip", reasons=[f"duplicate of {state['meta']['duplicate_of']}"], fit=fit, risk=risk.get("risk_score", 0))
    if risk.get("scam") or risk.get("risk_score", 0) > d.get("max_risk", 0.55):
        reasons.append(f"risk too high ({risk.get('risk_score', 0):.2f}): {risk.get('summary', '')}")
        return BidDecision(action="skip", reasons=reasons, fit=fit, risk=risk.get("risk_score", 0))
    budget = float(job.get("budget") or 0)
    if floor and budget:
        if job.get("budget_type") == "hourly" and budget < floor * d.get("min_budget_floor_ratio", 0.7):
            return BidDecision(action="skip", reasons=[f"hourly budget ${budget:.0f} is far below your floor ${floor:.0f}"], fit=fit,
                               risk=risk.get("risk_score", 0))
        if job.get("budget_type") == "fixed" and budget < floor * d.get("min_fixed_hours", 8):
            return BidDecision(action="skip", reasons=[f"fixed budget ${budget:.0f} is under {d.get('min_fixed_hours', 8)} hours at your floor"],
                               fit=fit, risk=risk.get("risk_score", 0))
    if fit >= d.get("bid_min_fit", 0.45):
        reasons.append(f"fit {fit:.2f} >= {d.get('bid_min_fit')}")
        action = "bid"
    elif fit >= d.get("watch_min_fit", 0.3):
        reasons.append(f"fit {fit:.2f} is borderline: watch")
        action = "watch"
    else:
        reasons.append(f"fit {fit:.2f} too low: outside your portfolio")
        action = "skip"
    if risk.get("injection_detected"):
        reasons.append("post contains instructions aimed at AI tools (ignored)")
    return BidDecision(action=action, reasons=reasons, fit=fit, risk=risk.get("risk_score", 0))


@node("decide")
async def decision(state: dict) -> dict:
    dec = decide(state)
    status = {"skip": "skipped", "watch": "watching", "bid": "analysing"}[dec.action]
    return {"decision": dec.model_dump(), "status": status, "status_reason": "; ".join(dec.reasons),
            "_summary": f"{dec.action}: {'; '.join(dec.reasons)}"}
