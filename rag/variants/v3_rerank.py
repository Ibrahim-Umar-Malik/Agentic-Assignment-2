"""V3 reranking: hybrid candidates re-scored by a cross-encoder (bge-reranker-v2-m3, or the lexical stand-in)."""

from ..pipeline import Options

NAME = "v3_rerank"
GROUP = "retrieval"
OPTIONS = Options(hybrid=True, rerank=True)
