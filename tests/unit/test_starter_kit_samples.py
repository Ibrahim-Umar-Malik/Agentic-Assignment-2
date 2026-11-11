"""The instructor starter kit's sample data (tests/fixtures/starter_kit, copied unchanged from
GigBid_Student_Starter_Kit_v0.1) run through GigBid's own components."""

import json
from pathlib import Path

from agent.nodes.risk import assess

KIT = Path(__file__).resolve().parents[1] / "fixtures" / "starter_kit"


def kit(name: str) -> list[dict]:
    return json.loads((KIT / name).read_text())


def as_job(j: dict) -> dict:
    return {"id": j["job_id"], "title": j["title"], "description": j["description"], "skills": j["required_skills"],
            "budget_type": "fixed", "budget": j["budget"]["max"], "connects_cost": j["connects_cost"],
            "screening_questions": j["screening_questions"]}


def client(c: dict) -> dict:
    return {"payment_verified": c["payment_verified"], "total_spent": 3000, "hires": c["completed_projects"],
            "avg_rating": c["average_rating"]}


def test_kit_legitimate_job_is_not_a_scam():
    job = as_job(kit("jobs.json")[0])
    r = assess(job, client(kit("client_history.json")[0]))
    assert not r.scam and r.risk_score < 0.35


def test_kit_unpaid_trial_with_off_platform_contact_is_a_scam():
    job = as_job(kit("jobs.json")[1])
    r = assess(job, client(kit("client_history.json")[0]))
    kinds = {f.kind for f in r.flags}
    # the kit marks it with warning_signals ["unpaid_work", "off_platform_contact"]; both must be found
    assert r.scam and {"free_work", "off_platform"} <= kinds


def test_kit_policy_rules_are_covered_by_our_policy_pack():
    """Each of the kit's seven illustrative rules maps to a rule id in data/policy_pack (docs/STARTER_KIT.md)."""
    ours = (Path(__file__).resolve().parents[2] / "data" / "policy_pack" / "policy.md").read_text()
    for rule_id in ["P1", "P2", "P3", "P4", "P5", "P6"]:
        assert f"**{rule_id}" in ours
