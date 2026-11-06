"""Risk Assessor: client quality from history, scams, free-work and off-platform asks, injected instructions."""

from __future__ import annotations

import re
from datetime import date

from core import llm

from ..handoffs import RiskFlag, RiskReport
from ..mcp_client import ToolGateway
from .common import injection_spans, load_prompt, node, risk_patterns, sanitize_untrusted, wrap


def client_quality(c: dict) -> tuple[float, list[RiskFlag]]:
    cfg = risk_patterns()["client"]
    flags: list[RiskFlag] = []
    q = 0.5
    if c.get("payment_verified") is False:
        flags.append(RiskFlag(kind="unverified_payment", severity=cfg["unverified_payment"], evidence="payment not verified"))
        q -= 0.25
    spent, hires = float(c.get("total_spent") or 0), int(c.get("hires") or 0)
    if spent <= 0 and hires == 0:
        flags.append(RiskFlag(kind="new_client", severity=cfg["new_client_no_spend"], evidence="no spend or hires yet"))
        q -= 0.1
    q += min(0.3, spent / 50000) + min(0.15, hires / 100)
    rating = c.get("avg_rating")
    if rating is not None and rating < cfg["low_rating_below"]:
        flags.append(RiskFlag(kind="other", severity=cfg["low_rating_penalty"], evidence=f"avg rating {rating}"))
        q -= 0.1
    try:
        if c.get("member_since") and (date.today() - date.fromisoformat(c["member_since"])).days < 90:
            q -= 0.1
    except ValueError:
        pass
    return max(0.0, min(1.0, q)), flags


def assess(job: dict, client: dict) -> RiskReport:
    text = f"{job.get('title', '')}. {job.get('description', '')}"
    # Scam patterns run on the post with injected instructions removed: an attacker's "include your email" line
    # is an injection (neutralised), not evidence that the client harvests contacts (report section 8).
    clean, _ = sanitize_untrusted(text)
    flags: list[RiskFlag] = []
    for p in risk_patterns()["scam"]:
        m = re.search(p["pattern"], clean)
        if m:
            flags.append(RiskFlag(kind=p["kind"], severity=p["severity"], evidence=clean[max(0, m.start() - 40): m.end() + 40]))
    inj = injection_spans(text)
    if inj:
        flags.append(RiskFlag(kind="injection", severity=0.3, evidence="; ".join(inj)[:200]))
    q, cflags = client_quality(client or {})
    flags += cflags
    scam = any(f.kind in ("scam", "advance_fee", "off_platform", "free_work", "contact_harvest") and f.severity >= 0.75 for f in flags)
    # Injection is flagged and neutralised (sanitise + delimit + compliance) but does not make the client risky:
    # counting it skipped 7 legitimate test-split jobs (evals/results/failures.json, report section 8).
    risk = max([f.severity for f in flags if f.kind != "injection"] + [0.0])
    if not scam:
        risk = min(1.0, risk * 0.6 + (1 - q) * 0.4) if any(f.kind != "injection" for f in flags) else (1 - q) * 0.4
    return RiskReport(risk_score=round(risk, 3), client_quality=round(q, 3), flags=flags, injection_detected=bool(inj), scam=scam,
                      summary=("Likely scam: " + ", ".join(sorted({f.kind for f in flags if f.severity >= 0.75}))) if scam else
                      f"Client quality {q:.2f}; {len(flags)} flag(s).")


@node("risk")
async def risk(state: dict) -> dict:
    job = state["job"]
    client = state.get("client") or {}
    if not client and job.get("client_id"):
        client = await ToolGateway(state["user_id"]).call("risk", "marketplace", "get_client_history", {"client_id": job["client_id"]})
    report = assess(job, client)
    if not llm.is_offline("risk") and not report.scam:
        # second opinion from the small model; it may only ADD flags (rules stay authoritative)
        _, system = load_prompt("risk")
        extra = await llm.call("risk", system, wrap("untrusted_job_post", job.get("description", "")) +
                               "\n" + wrap("untrusted_client_profile", str(client)), RiskReport)
        if extra is not None and extra.scam and extra.risk_score > report.risk_score:
            report.flags += [f for f in extra.flags if f.kind not in {x.kind for x in report.flags}]
            report.risk_score = max(report.risk_score, min(extra.risk_score, 0.9))
            report.summary += " Model flagged additional risk."
    return {"risk": report.model_dump(), "client": client, "_summary": report.summary}
