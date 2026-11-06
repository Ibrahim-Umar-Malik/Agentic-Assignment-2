"""Config shim so rag/ also works inside the standalone Portfolio MCP package (without GigBid's core/)."""

from __future__ import annotations

from typing import Any

try:
    from core import config as _cfg

    def get(path: str, default: Any = None) -> Any:
        return _cfg.get(path, default)
except ImportError:  # standalone gigbid-portfolio-mcp install
    import os

    _DEFAULTS = {"retrieval.embedder": os.environ.get("GIGBID_EMBEDDER", "hash"),
                 "retrieval.reranker": os.environ.get("GIGBID_RERANKER", "lexical"),
                 "retrieval.variant": os.environ.get("GIGBID_RAG_VARIANT", "v3_rerank_v1_decompose")}

    def get(path: str, default: Any = None) -> Any:
        return _DEFAULTS.get(path, default)
