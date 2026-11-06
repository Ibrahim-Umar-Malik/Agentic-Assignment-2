"""Explicit promotion rules (R7). Outcomes and user edits update long-term memory ONLY through these functions.

Style memory (from the user's edits to drafts):
  1. Every approved edit is diffed into candidate patterns: a phrase the user deleted, the first sentence cut,
     a large length cut, a sign-off added.
  2. A candidate is promoted to ("style", user) only when it has been seen in >= memory.style.min_occurrences
     DISTINCT threads. One-off edits never become rules. Raw edit text is never stored in memory.
Outcome memory (from marketplace outcomes):
  3. Per category, proposals are bucketed by opening type (question / evidence / generic). An insight is promoted
     to ("outcome", user, category) only with >= memory.outcome.min_samples outcomes in the category and a reply-rate
     difference >= memory.outcome.min_reply_rate_delta between the best bucket and the rest.
"""

from __future__ import annotations

import difflib
import re
import time
from typing import Any

from langgraph.store.base import BaseStore

from core import config

PHRASE_RX = re.compile(r"[a-z][a-z' -]{3,40}")


def first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0] if text.strip() else ""


def diff_edit(before: str, after: str) -> dict[str, Any]:
    """Structured diff of a human edit (also shown in the UI)."""
    sm = difflib.SequenceMatcher(None, before.split(), after.split())
    removed, added = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("delete", "replace"):
            removed.append(" ".join(before.split()[i1:i2]))
        if op in ("insert", "replace"):
            added.append(" ".join(after.split()[j1:j2]))
    return {"removed": removed, "added": added, "ratio": round(sm.ratio(), 3),
            "len_before": len(before.split()), "len_after": len(after.split())}


def candidates_from_edit(before: str, after: str) -> list[tuple[str, str]]:
    """(key, human-readable rule) candidates suggested by one edit."""
    d = diff_edit(before, after)
    out: list[tuple[str, str]] = []
    fb, fa = first_sentence(before), first_sentence(after)
    if fb and fb not in after and fa != fb:
        out.append(("cut_first_sentence", "Start with the second idea: cut the generic first sentence."))
    for chunk in d["removed"]:
        for w in re.findall(r"[A-Za-z']{5,}", chunk.lower()):
            if w not in after.lower() and w in {"passionate", "hardworking", "perfect", "guarantee", "expert", "excited",
                                                "dedicated", "seamless", "leverage", "synergy", "ninja", "rockstar", "immediately"}:
                out.append((f"never_say:{w}", f"Never use the word '{w}'."))
    if d["len_before"] and d["len_after"] < 0.75 * d["len_before"]:
        out.append(("shorter", f"Keep proposals short (user cut ~{100 - int(100 * d['len_after'] / d['len_before'])}% of the length)."))
    last_b, last_a = before.strip().split("\n")[-1], after.strip().split("\n")[-1]
    if last_a != last_b and re.match(r"(?i)^(best|thanks|cheers|regards)", last_a.strip()):
        out.append((f"signoff:{last_a.strip()[:20].lower()}", f"Sign off with '{last_a.strip()[:40]}'."))
    return list(dict.fromkeys(out))


async def record_edit(store: BaseStore, user_id: str, thread_id: str, before: str, after: str) -> list[str]:
    """Count candidates per distinct thread; promote those that pass the rule. Returns promoted keys."""
    min_occ = config.get("memory.style.min_occurrences", 2)
    promoted = []
    for key, rule in candidates_from_edit(before, after):
        item = await store.aget(("candidates", user_id), key)
        threads = set((item.value if item else {}).get("threads", []))
        threads.add(thread_id)
        await store.aput(("candidates", user_id), key, {"rule": rule, "threads": sorted(threads), "updated": time.time()})
        if len(threads) >= min_occ and await store.aget(("style", user_id), key) is None:
            existing = await store.asearch(("style", user_id), limit=1000)
            if len(existing) < config.get("memory.style.max_items", 30):
                await store.aput(("style", user_id), key, {"rule": rule, "promoted_by": "style.min_occurrences",
                                                           "support_threads": len(threads), "promoted_at": time.time()})
                promoted.append(key)
    return promoted


def opening_type(text: str) -> str:
    fs = first_sentence(text).lower()
    if "?" in fs:
        return "question"
    if re.search(r"(?i)dear|passionate|perfect fit|i am very interested|hello|hi there", fs):
        return "generic"
    return "evidence"


async def record_outcome(store: BaseStore, user_id: str, category: str, cover_letter: str, outcome: str) -> str | None:
    """Accumulate outcome stats in candidates; promote an insight when the rule's thresholds are met."""
    if not category:
        return None
    key = f"outcomes:{category}"
    item = await store.aget(("candidates", user_id), key)
    stats = (item.value if item else {}).get("buckets", {})
    b = stats.setdefault(opening_type(cover_letter), {"n": 0, "replied": 0, "won": 0})
    b["n"] += 1
    b["replied"] += outcome in ("replied", "interview", "hired")
    b["won"] += outcome == "hired"
    await store.aput(("candidates", user_id), key, {"buckets": stats, "updated": time.time()})
    n = sum(x["n"] for x in stats.values())
    if n < config.get("memory.outcome.min_samples", 3):
        return None
    rates = {k: v["replied"] / v["n"] for k, v in stats.items() if v["n"]}
    best = max(rates, key=rates.get)
    rest = [v for k, v in stats.items() if k != best]
    rest_rate = sum(x["replied"] for x in rest) / max(1, sum(x["n"] for x in rest)) if rest else 0.0
    if rates[best] - rest_rate >= config.get("memory.outcome.min_reply_rate_delta", 0.15):
        await store.aput(("outcome", user_id, category), "best_opening", {
            "rule": f"In {category}, {best}-style openings got replies {rates[best]:.0%} of the time vs {rest_rate:.0%} for others "
                    f"(n={n}).", "opening": best, "n": n, "promoted_by": "outcome.min_samples+min_reply_rate_delta",
            "promoted_at": time.time()})
        return "best_opening"
    return None
