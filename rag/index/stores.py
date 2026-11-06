"""Index structures: dense vector index (in-process, persisted to disk), BM25, and rerankers."""

from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache

import numpy as np

from ..types import Chunk, tokenize


class VectorIndex:
    """Exact cosine search over L2-normalised vectors. At GigBid's scale (hundreds to a few thousand chunks per
    freelancer) exact search is under a few milliseconds, so an ANN service would add ops cost without benefit
    (see docs/adr/0003-vector-store.md). Persisted next to the corpus in data/processed/."""

    def __init__(self, chunks: list[Chunk], vectors: np.ndarray):
        self.chunks = chunks
        self.vectors = vectors

    def search(self, qvec: np.ndarray, k: int, allow: set[int] | None = None) -> list[tuple[int, float]]:
        if not len(self.chunks):
            return []
        sims = self.vectors @ qvec.reshape(-1)
        if allow is not None:
            mask = np.full(len(sims), -np.inf)
            idx = list(allow)
            mask[idx] = sims[idx]
            sims = mask
        top = np.argsort(-sims)[:k]
        return [(int(i), float(sims[i])) for i in top if np.isfinite(sims[i])]


class BM25:
    def __init__(self, chunks: list[Chunk], k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [tokenize(c.text + " " + " ".join(c.meta.get("skills", []) if c.meta.get("type") != "cv" else [])) for c in chunks]
        self.tf = [Counter(d) for d in self.docs]
        self.len = np.array([len(d) for d in self.docs], dtype=np.float32)
        self.avg = float(self.len.mean()) if len(self.len) else 1.0
        df: Counter = Counter()
        for d in self.docs:
            df.update(set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int, allow: set[int] | None = None) -> list[tuple[int, float]]:
        q = tokenize(query)
        scores = np.zeros(len(self.docs), dtype=np.float32)
        for t in set(q):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i, tf in enumerate(self.tf):
                f = tf.get(t)
                if f:
                    scores[i] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
        if allow is not None:
            keep = np.zeros_like(scores, dtype=bool)
            keep[list(allow)] = True
            scores = np.where(keep, scores, 0)
        top = np.argsort(-scores)[:k]
        return [(int(i), float(scores[i])) for i in top if scores[i] > 0]


def rrf(rankings: list[list[tuple[int, float]]], k: int = 60) -> list[tuple[int, float]]:
    agg: dict[int, float] = {}
    for ranking in rankings:
        for rank, (i, _) in enumerate(ranking):
            agg[i] = agg.get(i, 0.0) + 1.0 / (k + rank + 1)
    return sorted(agg.items(), key=lambda x: -x[1])


class LexicalReranker:
    """Dependency-free reranker: query-term coverage with IDF, exact skill-name matches and phrase proximity.
    Stand-in for a cross-encoder where model weights are unavailable; results files record which ran."""

    name = "lexical"

    def __init__(self, idf: dict[str, float] | None = None):
        self.idf = idf or {}

    def score(self, query: str, texts: list[str]) -> list[float]:
        q = [t for t in tokenize(query)]
        qset = set(q)
        qbi = {f"{a} {b}" for a, b in zip(q, q[1:], strict=False)}
        out = []
        for t in texts:
            toks = tokenize(t)
            ts = set(toks)
            cov = sum(self.idf.get(w, 1.0) for w in qset & ts) / max(1e-9, sum(self.idf.get(w, 1.0) for w in qset))
            bi = {f"{a} {b}" for a, b in zip(toks, toks[1:], strict=False)}
            prox = len(qbi & bi) / max(1, len(qbi))
            out.append(0.8 * cov + 0.2 * prox)
        return out


class CrossEncoderReranker:
    def __init__(self, model: str):
        from sentence_transformers import CrossEncoder  # optional extra

        self.name = f"cross-encoder:{model}"
        self.model = CrossEncoder(model, device="cpu")

    def score(self, query: str, texts: list[str]) -> list[float]:
        return [float(s) for s in self.model.predict([(query, t) for t in texts])]


@lru_cache(maxsize=4)
def get_reranker(spec: str = "lexical"):
    if spec.startswith("cross-encoder:"):
        return CrossEncoderReranker(spec.split(":", 1)[1])
    return LexicalReranker()


def numbers_in(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text))
