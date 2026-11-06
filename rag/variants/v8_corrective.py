"""V8 corrective RAG: grade evidence per requirement, re-query with expansion when weak, refuse to claim when none."""

from ..pipeline import Options

NAME = "v8_corrective"
GROUP = "agentic"
OPTIONS = Options(decompose=True, hybrid=True, corrective=True)
