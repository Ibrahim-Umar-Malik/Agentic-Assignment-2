"""Shared helpers for eval runners. Every number in the README / report is read from evals/results/*.json,
which these runners write together with the settings that produced it (profile, embedder, split, commit)."""

from __future__ import annotations

import json
import math
import os
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / "evals" / "datasets"
RESULTS = ROOT / "evals" / "results"
PERSONAS = ["ai_ml", "fullstack", "data_analyst"]


def load_dev(persona: str) -> list[dict]:
    return [json.loads(line) for line in (DATASETS / f"dev_{persona}.jsonl").read_text().splitlines() if line.strip()]


def split(rows: list[dict], part: str) -> list[dict]:
    """Fixed split: 70% tune (choose variants/thresholds), 30% test (report). Never tune on 'test'."""
    if part == "all":
        return rows
    keep = (lambda i: i % 10 < 7) if part == "tune" else (lambda i: i % 10 >= 7)
    return [r for i, r in enumerate(rows) if keep(i)]


def public_job(row: dict) -> dict:
    """What the agent may see: strip gold labels and generator metadata."""
    return {k: v for k, v in row.items() if not k.startswith("_")}


def recall_at(ranked: list[str], gold: list[str], k: int) -> float:
    return len(set(ranked[:k]) & set(gold)) / len(gold) if gold else 0.0


def mrr(ranked: list[str], gold: list[str]) -> float:
    for i, p in enumerate(ranked, 1):
        if p in gold:
            return 1.0 / i
    return 0.0


def ndcg_at(ranked: list[str], gold: list[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 1) for i, p in enumerate(ranked[:k], 1) if p in gold)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(gold), k) + 1))
    return dcg / ideal if ideal else 0.0


def pctile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    i = min(len(s) - 1, max(0, math.ceil(p / 100 * len(s)) - 1))
    return s[i]


def mean(xs: list[float]) -> float | None:
    return round(statistics.fmean(xs), 4) if xs else None


def bootstrap_ci(xs: list[float], n: int = 1000, seed: int = 4016) -> list[float] | None:
    import random

    if len(xs) < 2:
        return None
    rng = random.Random(seed)
    ms = sorted(statistics.fmean(rng.choices(xs, k=len(xs))) for _ in range(n))
    return [round(ms[int(0.025 * n)], 4), round(ms[int(0.975 * n)], 4)]


def cohen_kappa(a: list[Any], b: list[Any]) -> float | None:
    if not a or len(a) != len(b):
        return None
    labels = sorted(set(a) | set(b), key=str)
    n = len(a)
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pe = sum((a.count(lab) / n) * (b.count(lab) / n) for lab in labels)
    return round((po - pe) / (1 - pe), 4) if pe < 1 else 1.0


def run_meta(**extra: Any) -> dict:
    from core import config

    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except Exception:
        sha = ""
    return {"commit": sha, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "profile": os.environ.get("GIGBID_PROFILE") or config.get("profile", "open"),
            "embedder": os.environ.get("GIGBID_EMBEDDER") or config.get("retrieval.embedder", "hash"),
            "reranker": os.environ.get("GIGBID_RERANKER") or config.get("retrieval.reranker", "lexical"),
            "data": "stand-in GigSim + personas (official starter kit not available at build time)", **extra}


def write_result(name: str, payload: dict) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"wrote {path.relative_to(ROOT)}")
    return path


def eval_env() -> None:
    """Isolated, deterministic environment for runners that execute the graph."""
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="gigbid-eval-"))
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{tmp / 'eval.db'}")
    os.environ.setdefault("GIGSIM_STATE", str(tmp / "gigsim.json"))
    os.environ.setdefault("GIGSIM_ERROR_RATE", "0")
    os.environ.setdefault("GIGBID_MCP_INPROCESS", "1")
    os.environ.setdefault("MARKETPLACE_ALLOW_ANON", "1")
