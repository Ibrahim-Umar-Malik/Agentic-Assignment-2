"""V4 outcome-aware ranking: boost evidence and phrasing from proposals that won or got replies."""

from ..pipeline import Options

NAME = "v4_outcome"
GROUP = "ranking"
OPTIONS = Options(hybrid=True, outcome=True)
