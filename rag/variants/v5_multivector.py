"""V5 multi-vector items: summary, README, code and proposal chunks indexed separately, returned as one project."""

from ..pipeline import Options

NAME = "v5_multivector"
GROUP = "indexing"
OPTIONS = Options(hybrid=True, multivector=True)
