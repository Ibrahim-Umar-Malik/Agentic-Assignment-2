"""Retriever factory: the deployed variant is chosen by config (retrieval.variant), set from the evaluation."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from . import _config as config

from .ingest.loaders import load_persona
from .pipeline import Options, PortfolioIndex, RetrievalResult
from .variants import options_for

ROOT = Path(__file__).resolve().parents[1]
PERSONAS_DIR = Path(os.environ.get("GIGBID_PERSONAS_DIR", ROOT / "data" / "personas"))
USER_DIR = Path(os.environ.get("GIGBID_USER_PORTFOLIO_DIR", ROOT / "var" / "portfolio"))

_cache: dict[str, PortfolioIndex] = {}
_lock = threading.Lock()


def corpus_key(persona: str, user_id: str | None = None) -> str:
    return f"{persona}:{user_id or '-'}"


def get_index(persona: str, user_id: str | None = None, embedder: str | None = None) -> PortfolioIndex:
    key = corpus_key(persona, user_id) + f":{embedder or ''}"
    with _lock:
        if key not in _cache:
            pdir = PERSONAS_DIR / persona
            docs = load_persona(pdir) if pdir.exists() else []
            udir = USER_DIR / (user_id or "_none")
            if user_id and udir.exists():
                docs += [d for d in load_persona(udir) if d.meta.get("type") != "cv" or not docs]
            _cache[key] = PortfolioIndex(pdir if pdir.exists() else udir, embedder=embedder, docs=docs)
        return _cache[key]


def invalidate(persona: str, user_id: str | None = None) -> None:
    with _lock:
        for k in [k for k in _cache if k.startswith(corpus_key(persona, user_id))]:
            _cache.pop(k, None)


def shipped_options() -> Options:
    return options_for(config.get("retrieval.variant", "v2_hybrid"))


def retrieve_for_job(persona: str, job: dict, requirements: list[str] | None = None, user_id: str | None = None,
                     hypothetical: str | None = None, deleted: set[str] | None = None) -> RetrievalResult:
    return get_index(persona, user_id).retrieve(job, shipped_options(), requirements, hypothetical, deleted)
