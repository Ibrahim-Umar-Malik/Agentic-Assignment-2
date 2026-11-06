"""Embedders. Open models in every profile; `hash` is a dependency-free fallback for CI and offline runs.

* hash: signed feature hashing of word unigrams, bigrams and character 4-grams, sub-linear TF, L2-normalised.
  It is not a neural model; it is the CPU floor every other embedder must beat, and lets the full system run
  where model weights cannot be downloaded. Results files record which embedder produced them.
* sentence-transformers:<model>: e.g. BAAI/bge-small-en-v1.5, nomic-ai/nomic-embed-text-v1.5, Qwen/Qwen3-Embedding-0.6B.
* ollama:<model>: e.g. nomic-embed-text via the Ollama service in docker compose.
"""

from __future__ import annotations

import hashlib
import math
import os
from functools import lru_cache

import numpy as np

from ..types import tokenize


class HashEmbedder:
    name = "hash"

    def __init__(self, dim: int = 1024):
        self.dim = dim

    def _features(self, text: str) -> dict[int, float]:
        toks = tokenize(text)
        feats: dict[int, float] = {}

        def add(f: str, w: float) -> None:
            h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "little")
            idx, sign = h % self.dim, (1.0 if (h >> 63) & 1 else -1.0)
            feats[idx] = feats.get(idx, 0.0) + sign * w

        for t in toks:
            add("w:" + t, 1.0)
            padded = f"#{t}#"
            for i in range(max(1, len(padded) - 3)):
                add("c:" + padded[i: i + 4], 0.25)
        for a, b in zip(toks, toks[1:], strict=False):
            add("b:" + a + "_" + b, 0.6)
        return feats

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for idx, v in self._features(t).items():
                out[i, idx] = math.copysign(math.log1p(abs(v)), v)
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.maximum(norms, 1e-9)


class STEmbedder:
    def __init__(self, model: str):
        from sentence_transformers import SentenceTransformer  # optional extra: pip install .[models]

        self.name = f"sentence-transformers:{model}"
        self.model = SentenceTransformer(model, device="cpu")

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self.model.encode(texts, normalize_embeddings=True, batch_size=32), dtype=np.float32)


class OllamaEmbedder:
    def __init__(self, model: str):
        self.name = f"ollama:{model}"
        self.model = model
        self.url = os.environ.get("OLLAMA_URL", "http://ollama:11434")

    def embed(self, texts: list[str]) -> np.ndarray:
        import httpx

        r = httpx.post(f"{self.url}/api/embed", json={"model": self.model, "input": texts}, timeout=120)
        r.raise_for_status()
        v = np.asarray(r.json()["embeddings"], dtype=np.float32)
        return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)


@lru_cache(maxsize=4)
def get_embedder(spec: str = "hash"):
    if spec == "hash":
        return HashEmbedder()
    kind, _, model = spec.partition(":")
    if kind == "sentence-transformers":
        return STEmbedder(model)
    if kind == "ollama":
        return OllamaEmbedder(model)
    raise ValueError(f"unknown embedder {spec}")
