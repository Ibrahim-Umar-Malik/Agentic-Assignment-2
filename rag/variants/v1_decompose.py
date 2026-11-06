"""V1 requirement decomposition: one retrieval per extracted requirement, merged with RRF."""

from ..pipeline import Options

NAME = "v1_decompose"
GROUP = "query"
OPTIONS = Options(decompose=True)
