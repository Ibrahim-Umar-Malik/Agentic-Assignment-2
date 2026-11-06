"""V6 contextual retrieval: a generated context line is prepended to each chunk before embedding."""

from ..pipeline import Options

NAME = "v6_contextual"
GROUP = "indexing"
OPTIONS = Options(hybrid=True, contextual=True)
