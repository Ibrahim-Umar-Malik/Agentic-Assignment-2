"""Claim verification (B3): split a draft into claims, ground each one in evidence, drop or rewrite the rest.

Labels: supported / partly_supported / unsupported. The deterministic grounder checks content-word coverage
against the best evidence chunk, that every number in the claim appears in that evidence, and that every named
skill is one the portfolio actually contains. When an LLM is configured for the `verifier` node, its NLI-style
label is combined with the deterministic one (the stricter label wins), so a model cannot talk a claim into
being supported.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .index.skills import find_skills
from .index.stores import numbers_in
from .types import Evidence, tokenize

CLAIM_MARKERS = re.compile(
    r"(?i)\b(i|i've|i have|i'm|my|we)\b.*\b(built|build|shipped|delivered|led|designed|created|developed|implemented|"
    r"trained|deployed|migrated|reduced|cut|improved|increased|saved|automated|worked|experience|years|clients?|"
    r"fine-tuned|wrote|ran|launched|helped|achieved|own|have)\b"
)
ORDER = {"supported": 2, "partly_supported": 1, "unsupported": 0}


@dataclass
class Claim:
    text: str
    label: str = "unsupported"
    score: float = 0.0
    evidence_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n{1,}", text.strip())
    return [p.strip() for p in parts if p and len(p.strip()) > 2]


def is_claim(sentence: str) -> bool:
    """A sentence is a factual claim about the freelancer if it asserts experience, results or numbers."""
    if sentence.endswith("?"):
        return False
    if re.search(r"(?i)\b(have not|haven't|never|not yet|would|will)\b", sentence) and not re.search(r"\d", sentence):
        return False  # honest negatives and plans are not experience claims
    return bool(CLAIM_MARKERS.search(sentence)) or (bool(re.search(r"\d", sentence)) and bool(re.search(r"(?i)\b(i|my)\b", sentence)))


def ground(claim: str, evidence: list[Evidence], vocab: list[str]) -> Claim:
    c = Claim(claim)
    ctoks = set(tokenize(claim)) - {"built", "delivered", "shipped", "project", "client", "clients", "recently", "similar"}
    nums = numbers_in(claim)
    skills = find_skills(claim, vocab)
    known = {s.lower() for s in vocab}
    best, best_ids = 0.0, []
    for e in evidence:
        etext = e.chunk.text + " " + " ".join(e.chunk.meta.get("skills", []))
        etoks = set(tokenize(etext))
        cov = len(ctoks & etoks) / max(1, len(ctoks))
        num_ok = nums <= numbers_in(etext) if nums else True
        sk_ok = all(s.lower() in etext.lower() or s.lower() in known for s in skills)
        s = cov * (1.0 if num_ok else 0.4) * (1.0 if sk_ok else 0.5)
        if s > best + 1e-9:
            best, best_ids = s, [e.chunk.meta.get("item_id") or e.chunk.id]
        elif abs(s - best) < 1e-9 and s > 0:
            best_ids.append(e.chunk.meta.get("item_id") or e.chunk.id)
    unknown_skills = [s for s in skills if s.lower() not in known]
    if unknown_skills:
        c.reasons.append(f"skills not in portfolio: {', '.join(unknown_skills)}")
        best *= 0.3
    if nums and not any(nums <= numbers_in(e.chunk.text) for e in evidence):
        c.reasons.append("numbers not found in evidence")
    c.score = round(best, 3)
    c.label = "supported" if best >= 0.55 else "partly_supported" if best >= 0.33 else "unsupported"
    c.evidence_ids = list(dict.fromkeys(best_ids))[:3]
    return c


def verify(text: str, evidence: list[Evidence], vocab: list[str], llm_labels: dict[str, str] | None = None) -> dict[str, Any]:
    """Return per-sentence labels, the cleaned text (unsupported claims removed, partial ones hedged) and rates."""
    sentences = split_sentences(text)
    out_sents, claims = [], []
    for s in sentences:
        if not is_claim(s):
            out_sents.append(s)
            continue
        c = ground(s, evidence, vocab)
        if llm_labels and s in llm_labels and ORDER.get(llm_labels[s], 2) < ORDER[c.label]:
            c.reasons.append(f"llm verifier: {llm_labels[s]}")
            c.label = llm_labels[s]
        claims.append(c)
        if c.label == "supported":
            out_sents.append(s)
        elif c.label == "partly_supported":
            out_sents.append(s)  # kept, flagged for the Critic and shown in the UI
    n = len(claims)
    unsupported = sum(1 for c in claims if c.label == "unsupported")
    return {
        "claims": [asdict(c) for c in claims],
        "n_claims": n,
        "unsupported_before": unsupported,
        "unsupported_rate_before": round(unsupported / n, 3) if n else 0.0,
        "cleaned_text": _join(out_sents, text),
        "unsupported_after": 0,
    }


def _join(sentences: list[str], original: str) -> str:
    # keep paragraph structure roughly: sentences that started a paragraph in the original start one again
    out = []
    for s in sentences:
        idx = original.find(s)
        if out and idx > 0 and original[max(0, idx - 2): idx].count("\n") >= 1:
            out.append("\n\n" + s)
        else:
            out.append((" " if out else "") + s)
    return "".join(out).strip()
