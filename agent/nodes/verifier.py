"""Claim verification node (B3): unsupported claims are removed before the Critic sees the draft."""

from __future__ import annotations

from pydantic import BaseModel

from core import llm
from rag.types import Chunk, Evidence
from rag.verify import is_claim, split_sentences, verify

from ..mcp_client import ToolGateway
from .common import load_prompt, node


class _Labels(BaseModel):
    labels: list[str]


def to_evidence(items: list[dict]) -> list[Evidence]:
    return [Evidence(Chunk(i["id"], (i.get("text") or i.get("snippet") or ""), i["id"],
                           {"item_id": i["id"], "skills": i.get("skills", []), "project": i.get("project"), "type": i.get("type")}),
                     float(i.get("score", 0))) for i in items]


@node("verifier")
async def verifier(state: dict) -> dict:
    gw = ToolGateway(state["user_id"])
    pid = (state.get("meta") or {}).get("portfolio_id") or state.get("persona")
    draft = dict(state["draft"])
    items = list(state.get("evidence") or [])
    for iid in draft.get("cited_items", [])[:5]:  # load full text of cited items so numbers can be checked
        try:
            cs = await gw.call("verifier", "portfolio", "get_case_study", {"id": iid, "portfolio_id": pid})
            items.append({"id": cs["id"], "text": cs["text"], "skills": cs.get("skills", []), "project": cs.get("project")})
        except Exception:
            pass
    skills = (await gw.call("verifier", "portfolio", "list_skills", {"portfolio_id": pid}))["skills"]
    vocab = [s["skill"] for s in skills if s["evidence_items"] > 0]
    ev = to_evidence(items)
    llm_labels = None
    if not llm.is_offline("verifier"):
        claims = [s for s in split_sentences(draft["cover_letter"]) if is_claim(s)]
        if claims:
            _, system = load_prompt("verifier")
            ctx = "\n".join(f"[{e.chunk.id}] {e.chunk.text[:500]}" for e in ev[:12])
            out = await llm.call("verifier", system, "EVIDENCE:\n" + ctx + "\n\nCLAIMS:\n" +
                                 "\n".join(f"{i + 1}. {c}" for i, c in enumerate(claims)), _Labels)
            if out and len(out.labels) == len(claims):
                llm_labels = dict(zip(claims, out.labels, strict=False))
    rep = verify(draft["cover_letter"], ev, vocab, llm_labels)
    after = verify(rep["cleaned_text"], ev, vocab)
    rep["unsupported_after"] = after["unsupported_before"]
    rep["unsupported_rate_after"] = after["unsupported_rate_before"]
    # screening answers are verified the same way
    answers = []
    for a in draft.get("screening_answers", []):
        r = verify(a["answer"], ev, vocab)
        rep["unsupported_before"] += r["unsupported_before"]
        rep["n_claims"] += r["n_claims"]
        answers.append({**a, "answer": r["cleaned_text"] or "I would rather discuss this on a short call."})
    rep["unsupported_rate_before"] = round(rep["unsupported_before"] / rep["n_claims"], 3) if rep["n_claims"] else 0.0
    draft.update(cover_letter=rep["cleaned_text"], screening_answers=answers,
                 claims=[{"text": c["text"], "label": c["label"], "evidence_ids": c["evidence_ids"], "score": c["score"]}
                         for c in after["claims"]])
    return {"draft": draft, "verification": {k: v for k, v in rep.items() if k != "cleaned_text"},
            "_summary": f"claims {rep['n_claims']}, unsupported {rep['unsupported_before']} -> {rep['unsupported_after']}"}
