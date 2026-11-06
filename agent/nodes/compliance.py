"""Compliance Guard: enforce the policy pack (data/policy_pack/rules.yaml): redact contact details, rewrite
guarantees, block off-platform payment / free work / over-length, and block unsupported claims a human added."""

from __future__ import annotations

import re

from core import config, llm

from ..handoffs import ComplianceVerdict, ComplianceViolation, ScreeningAnswer
from .common import load_prompt, node


def check_text(text: str, rules: list[dict], kind: str = "cover_letter") -> tuple[str, list[ComplianceViolation]]:
    vio: list[ComplianceViolation] = []
    for r in rules:
        if r.get("name") == "length":
            limit = r.get("max_cover_letter_chars" if kind == "cover_letter" else "max_screening_answer_chars", 5000)
            if len(text) > limit:
                vio.append(ComplianceViolation(rule_id=r["id"], detail=f"{kind} is {len(text)} chars (> {limit})", action="block"))
            continue
        for pat in r.get("patterns", []):
            for m in list(re.finditer(pat, text)):
                act = r.get("action", "block")
                vio.append(ComplianceViolation(rule_id=r["id"], detail=f"{r['name']}: '{m.group(0)[:60]}'", action=act))
                if act == "redact":
                    text = text.replace(m.group(0), "")
                elif act == "rewrite":
                    text = re.sub(r"(?i)\bguarantee[sd]?\b", "aim for", text)
                    text = re.sub(r"(?i)\b100\s?%\s?(results|success|satisfaction|accuracy)", r"strong \1", text)
    text = re.sub(r"[ \t]{2,}", " ", text).replace(" .", ".").strip()
    return text, vio


@node("compliance")
async def compliance(state: dict, key: str = "draft") -> dict:
    rules = config.policy_rules()["rules"]
    draft = dict(state[key])
    body_key = "cover_letter" if key == "draft" else "body"
    text, vio = check_text(draft[body_key], rules)
    answers = []
    for a in draft.get("screening_answers", []) or []:
        t, v = check_text(a["answer"], rules, "answer")
        vio += v
        answers.append(ScreeningAnswer(question=a["question"], answer=t))
    # P3: unsupported claims introduced by a human edit block until fixed (the agent's own were removed by the verifier)
    for cl in draft.get("claims", []) or []:
        if cl.get("label") == "unsupported":
            vio.append(ComplianceViolation(rule_id="P3", detail=f"claim not supported by your portfolio: '{cl['text'][:80]}'", action="block"))
    if not llm.is_offline("compliance"):
        _, system = load_prompt("compliance", policy=(config.ROOT / "data" / "policy_pack" / "policy.md").read_text())
        extra = await llm.call("compliance", system, text, ComplianceVerdict)
        if extra:  # may add violations, never remove them
            vio += [v for v in extra.violations if v.action == "block" and v.rule_id not in {x.rule_id for x in vio}]
    status = "block" if any(v.action == "block" for v in vio) else "fixed" if vio else "pass"
    draft[body_key] = text
    if answers:
        draft["screening_answers"] = [a.model_dump() for a in answers]
    verdict = ComplianceVerdict(status=status, violations=vio, cleaned_text=text, cleaned_answers=answers,
                                policy_version=config.policy_rules().get("version", 1))
    out = {"compliance": verdict.model_dump(), key: draft, "_summary": f"{status}: {len(vio)} violation(s)"}
    if status == "block":
        out.update(status="blocked", status_reason="; ".join(f"{v.rule_id} {v.detail}" for v in vio if v.action == "block"))
    return out
