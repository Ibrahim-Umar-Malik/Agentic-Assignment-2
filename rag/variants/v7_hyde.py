"""V7 HyDE: retrieve with a hypothetical ideal proposal for the job (LLM-written when a model is configured)."""

from ..pipeline import Options

NAME = "v7_hyde"
GROUP = "query"
OPTIONS = Options(hyde=True)
