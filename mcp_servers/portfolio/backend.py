"""Portfolio backend: one PortfolioIndex per corpus, loaded lazily.

Inside GigBid, `portfolio_id` is "<persona>" or "<persona>:<user_id>" and resolves through rag.retriever (so user
uploads and deletions apply). Standalone (Claude Desktop / Cursor), the corpus is a folder in GigBid's portfolio
format passed with --corpus or PORTFOLIO_DIR; a sample persona ships with the package.
"""

from __future__ import annotations

import os
from pathlib import Path

try:  # inside the GigBid repo
    from rag import retriever as _gigbid_retriever
    from rag.pipeline import Options, PortfolioIndex
except ImportError:  # installed as gigbid-portfolio-mcp (rag/ is vendored into the package)
    from .rag.pipeline import Options, PortfolioIndex  # type: ignore
    _gigbid_retriever = None

_PKG = Path(__file__).resolve().parent
_indexes: dict[str, PortfolioIndex] = {}
DEFAULT_OPTIONS = Options(decompose=False, hybrid=True, rerank=True, outcome=True)
if _gigbid_retriever is not None:  # inside GigBid the shipped variant (chosen by evaluation) is used
    from dataclasses import replace as _replace

    DEFAULT_OPTIONS = _replace(_gigbid_retriever.shipped_options(), decompose=False, hyde=False)


def default_corpus() -> Path:
    env = os.environ.get("PORTFOLIO_DIR")
    if env:
        return Path(env).expanduser()
    for cand in (_PKG / "sample_persona", _PKG.parents[1] / "data" / "personas" / "ai_ml"):
        if cand.exists():
            return cand
    raise FileNotFoundError("Set PORTFOLIO_DIR to your portfolio folder (see README)")


def get(portfolio_id: str | None = None) -> PortfolioIndex:
    if portfolio_id and _gigbid_retriever is not None and (_gigbid_retriever.PERSONAS_DIR / portfolio_id.split(":")[0]).exists():
        persona, _, user = portfolio_id.partition(":")
        return _gigbid_retriever.get_index(persona, user or None)
    key = str(default_corpus())
    if key not in _indexes:
        _indexes[key] = PortfolioIndex(default_corpus())
    return _indexes[key]
