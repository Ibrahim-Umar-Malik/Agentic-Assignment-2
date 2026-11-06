"""V0 baseline: fixed word-window chunks, top-k cosine on the whole job post."""

from ..pipeline import Options

NAME = "v0_naive"
GROUP = "baseline"
OPTIONS = Options(chunking="fixed")
