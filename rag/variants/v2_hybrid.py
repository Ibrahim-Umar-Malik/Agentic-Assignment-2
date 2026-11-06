"""V2 hybrid retrieval: BM25 plus dense, fused with reciprocal rank fusion (exact names like Celery, dbt)."""

from ..pipeline import Options

NAME = "v2_hybrid"
GROUP = "retrieval"
OPTIONS = Options(hybrid=True)
