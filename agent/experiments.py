"""Signature extension X2: proposal A/B experiments.

Each analysed job is assigned to one arm of the running experiment by a stable hash of (user, experiment, job), so a
re-run or a crash-and-resume never switches arms. The arm changes one thing the Writer does (default experiment:
whether the cover letter asks the client one specific clarifying question). Outcomes (reply / interview / hire) come back through the pipeline sync and are
compared per arm with a two-proportion z-test; a winner is only declared after the minimum sample size per arm and
p < alpha, and is then offered to the user (never applied silently).
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

from core import config


def active() -> dict | None:
    exp = config.get("experiments.opening", {}) or {}
    return exp if exp.get("enabled") else None


def assign(user_id: str, job_id: str, exp: dict | None = None) -> str | None:
    exp = exp or active()
    if not exp:
        return None
    arms: dict[str, float] = exp.get("arms") or {"statement": 0.5, "question": 0.5}
    h = int(hashlib.sha256(f"{user_id}|{exp.get('id', 'opening-v1')}|{job_id}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    acc = 0.0
    for name, w in arms.items():
        acc += w / sum(arms.values())
        if h <= acc:
            return name
    return list(arms)[-1]


def two_proportion(s_a: int, n_a: int, s_b: int, n_b: int) -> dict[str, Any]:
    """Two-sided two-proportion z-test (normal approximation) with a 95% CI for the difference b - a."""
    if not n_a or not n_b:
        return {"diff": None, "p_value": None, "ci95": None}
    pa, pb = s_a / n_a, s_b / n_b
    pool = (s_a + s_b) / (n_a + n_b)
    se0 = math.sqrt(pool * (1 - pool) * (1 / n_a + 1 / n_b)) or 1e-9
    z = (pb - pa) / se0
    p = math.erfc(abs(z) / math.sqrt(2))
    se = math.sqrt(pa * (1 - pa) / n_a + pb * (1 - pb) / n_b)
    return {"diff": round(pb - pa, 4), "z": round(z, 3), "p_value": round(p, 4),
            "ci95": [round(pb - pa - 1.96 * se, 4), round(pb - pa + 1.96 * se, 4)]}


def summarize(rows: list[dict], exp: dict | None = None) -> dict[str, Any]:
    """rows: [{"arm": str, "replied": bool}] for proposals that reached a final-enough stage."""
    exp = exp or active() or {}
    arms = list((exp.get("arms") or {"statement": 0.5, "question": 0.5}).keys())
    stats = {a: {"sent": sum(1 for r in rows if r.get("arm") == a), "replied": sum(1 for r in rows if r.get("arm") == a and r.get("replied"))}
             for a in arms}
    out: dict[str, Any] = {"experiment": exp.get("id", "opening-v1"), "metric": "reply rate", "arms": stats}
    if len(arms) >= 2:
        a, b = arms[0], arms[1]
        test = two_proportion(stats[a]["replied"], stats[a]["sent"], stats[b]["replied"], stats[b]["sent"])
        min_n = int(exp.get("min_per_arm", 30))
        alpha = float(exp.get("alpha", 0.05))
        ready = min(stats[a]["sent"], stats[b]["sent"]) >= min_n
        winner = None
        if ready and test["p_value"] is not None and test["p_value"] < alpha:
            winner = b if test["diff"] > 0 else a
        out.update(test=test, min_per_arm=min_n, alpha=alpha, ready=ready, winner=winner,
                   status="winner" if winner else "collecting" if not ready else "no significant difference")
    return out
