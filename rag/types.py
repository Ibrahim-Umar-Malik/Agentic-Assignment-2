"""Shared RAG data types."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

STOP = set("""a an the and or of to in on for with by at from as is are was were be been being this that these those it its
we our you your i me my they their them he she his her us not no but if then so than too very can will would should could
into over under about after before during while also just only own same such each any all both more most other some what
which who whom how when where why need needs needed looking someone experienced experience expert help want work working
project projects company team""".split())

TOKEN_RX = re.compile(r"[a-z0-9][a-z0-9+#.\-]*[a-z0-9+#]|[a-z0-9]")


def tokenize(text: str, keep_stop: bool = False) -> list[str]:
    toks = TOKEN_RX.findall(text.lower())
    return toks if keep_stop else [t for t in toks if t not in STOP]


@dataclass
class Chunk:
    id: str
    text: str
    doc_id: str
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def project(self) -> str | None:
        return self.meta.get("project")


@dataclass
class Evidence:
    chunk: Chunk
    score: float
    requirement: str | None = None
    signals: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        m = self.chunk.meta
        return {"id": self.chunk.id, "item_id": m.get("item_id"), "project": m.get("project"), "type": m.get("type"),
                "source": m.get("source"), "date": m.get("date"), "outcome": m.get("outcome"), "title": m.get("title"),
                "skills": m.get("skills", []), "text": self.chunk.text[:600], "score": round(self.score, 4),
                "requirement": self.requirement}
