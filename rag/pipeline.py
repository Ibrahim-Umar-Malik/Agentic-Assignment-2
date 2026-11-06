"""Configurable retrieval pipeline. Each variant in rag/variants/ is a preset of these options, so the full
comparison and the ablation are one command (evals/runners/rag_eval.py, evals/runners/ablation.py)."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np

from core import config

from .index.embed import get_embedder
from .index.skills import expand, find_skills
from .index.stores import BM25, VectorIndex, get_reranker, rrf
from .ingest.chunker import context_line, fixed_chunks, structured_chunks
from .ingest.loaders import Document, load_persona
from .types import Chunk, Evidence, tokenize


@dataclass(frozen=True)
class Options:
    chunking: str = "structured"     # fixed (V0) | structured
    contextual: bool = False         # V6: prepend a context line to each chunk before embedding
    decompose: bool = False          # V1: one retrieval per extracted requirement, then merge
    hybrid: bool = False             # V2: BM25 + dense with reciprocal rank fusion
    rerank: bool = False             # V3: cross-encoder (or lexical stand-in) reranking
    outcome: bool = False            # V4: boost evidence from proposals that won or got replies
    multivector: bool = False        # V5: summary / README / code / proposal indexed separately, returned as one project
    hyde: bool = False               # V7: retrieve with a hypothetical ideal proposal
    corrective: bool = False         # V8: grade evidence, re-query when weak, refuse to claim when none
    k: int = 8
    candidates: int = 30


@dataclass
class RetrievalResult:
    evidence: list[Evidence]
    by_requirement: dict[str, list[Evidence]] = field(default_factory=dict)
    unsupported: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)

    def projects(self) -> list[str]:
        seen: list[str] = []
        for e in self.evidence:
            p = e.chunk.project
            if p and p not in seen:
                seen.append(p)
        return seen


GROUPS = {"case_study": "summary", "cv": "summary", "review": "summary", "repo_readme": "readme", "repo_code": "code",
          "proposal": "proposal"}


class PortfolioIndex:
    """All index structures for one freelancer corpus. Re-indexing is incremental per document (by content hash)."""

    def __init__(self, corpus_dir: str | Path, embedder: str | None = None, docs: list[Document] | None = None):
        self.corpus_dir = Path(corpus_dir)
        self.embedder = get_embedder(embedder or config.get("retrieval.embedder", "hash"))
        self.docs = docs if docs is not None else load_persona(self.corpus_dir)
        self.profile = json.loads((self.corpus_dir / "profile.json").read_text()) if (self.corpus_dir / "profile.json").exists() else {}
        self.vocab = sorted(set(self.profile.get("skills", [])) | {s for d in self.docs for s in d.meta.get("skills", [])})
        self._build()

    def _build(self) -> None:
        self.fixed = [c for d in self.docs for c in fixed_chunks(d)]
        self.struct = [c for d in self.docs for c in structured_chunks(d)]
        self.fixed_vi = VectorIndex(self.fixed, self.embedder.embed([c.text for c in self.fixed]))
        self.struct_vi = VectorIndex(self.struct, self.embedder.embed([c.text for c in self.struct]))
        self.ctx_vi = VectorIndex(self.struct, self.embedder.embed([context_line(c.meta) + " " + c.text for c in self.struct]))
        self.bm25 = BM25(self.struct)
        self.groups: dict[str, set[int]] = defaultdict(set)
        for i, c in enumerate(self.struct):
            self.groups[GROUPS.get(c.meta.get("type"), "summary")].add(i)
        # outcome prior per project from past proposals: mean of configured boosts
        boosts = config.get("retrieval.outcome_boost", {"won": 0.35, "replied": 0.15, "ignored": -0.1})
        acc: dict[str, list[float]] = defaultdict(list)
        for d in self.docs:
            if d.meta.get("type") == "proposal" and d.meta.get("project"):
                acc[d.meta["project"]].append(boosts.get(d.meta.get("outcome"), 0.0))
        self.project_prior = {p: float(np.mean(v)) for p, v in acc.items()}
        self.by_item = {d.meta.get("item_id"): d for d in self.docs}

    def add_documents(self, docs: list[Document]) -> int:
        """Incremental re-index when the user adds work in the UI."""
        existing = {d.id for d in self.docs}
        new = [d for d in docs if d.id not in existing]
        if new:
            self.docs.extend(new)
            self._build()
        return len(new)

    def remove_item(self, item_id: str) -> int:
        before = len(self.docs)
        self.docs = [d for d in self.docs if d.meta.get("item_id") != item_id and d.id != item_id]
        if len(self.docs) != before:
            self._build()
        return before - len(self.docs)

    # ---------------- retrieval ----------------
    def extract_requirements(self, job: dict) -> list[str]:
        text = f"{job.get('title', '')}. {job.get('description', '')}"
        skills = list(dict.fromkeys((job.get("skills") or []) + find_skills(text, self.vocab)))
        if skills:
            return skills[:8]
        sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", job.get("description", "")) if len(tokenize(s)) >= 3]
        return sents[:4] or [job.get("title", "")]

    def hyde_text(self, job: dict, requirements: list[str]) -> str:
        return (f"I recently delivered a project for a client like you: {job.get('title', '')}. "
                f"I built it with {', '.join(requirements)}, and it produced measurable results. "
                f"Here is my case study and the repository.")

    def _rank_query(self, q: str, opts: Options, allow: set[int] | None = None) -> list[tuple[int, float]]:
        vi = self.fixed_vi if opts.chunking == "fixed" else (self.ctx_vi if opts.contextual else self.struct_vi)
        dense = vi.search(self.embedder.embed([q])[0], opts.candidates, allow)
        if opts.hybrid and opts.chunking != "fixed":
            return rrf([dense, self.bm25.search(q, opts.candidates, allow)], k=config.get("retrieval.rrf_k", 60))
        return dense

    def _rank(self, q: str, opts: Options) -> list[tuple[int, float]]:
        if opts.multivector and opts.chunking != "fixed":
            per_group = [self._rank_query(q, opts, allow) for allow in self.groups.values() if allow]
            return rrf(per_group, k=config.get("retrieval.rrf_k", 60))
        return self._rank_query(q, opts)

    def retrieve(self, job: dict, opts: Options, requirements: list[str] | None = None,
                 hypothetical: str | None = None, deleted: set[str] | None = None) -> RetrievalResult:
        chunks = self.fixed if opts.chunking == "fixed" else self.struct
        reqs = requirements or self.extract_requirements(job)
        whole = f"{job.get('title', '')}\n{job.get('description', '')}"
        queries: list[tuple[str | None, str]] = [(r, r) for r in reqs] if opts.decompose else [(None, whole)]
        if opts.hyde:
            queries.append((None, hypothetical or self.hyde_text(job, reqs)))
        rankings: list[list[tuple[int, float]]] = []
        attribution: dict[int, str] = {}
        by_req: dict[str, list[Evidence]] = {}
        unsupported: list[str] = []
        reranker = get_reranker(config.get("retrieval.reranker", "lexical")) if opts.rerank else None
        if reranker is not None and hasattr(reranker, "idf"):
            reranker.idf = self.bm25.idf
        min_score = config.get("retrieval.corrective.min_evidence_score", 0.12)
        for req, q in queries:
            ranking = self._rank(q, opts)
            if opts.corrective and req is not None:
                grade = self._grade(req, ranking, chunks)
                if grade < min_score:
                    ranking = self._rank(expand(q), opts)
                    grade = self._grade(req, ranking, chunks)
                    if grade < min_score:
                        unsupported.append(req)
                        continue  # refuse to claim: no evidence for this requirement
            if reranker is not None:
                cand = ranking[: opts.candidates]
                scores = reranker.score(q, [chunks[i].text + " " + " ".join(chunks[i].meta.get("skills", [])) for i, _ in cand])
                ranking = sorted(((i, s) for (i, _), s in zip(cand, scores, strict=False)), key=lambda x: -x[1])
            rankings.append(ranking)
            if req is not None:
                by_req[req] = [Evidence(chunks[i], s, req) for i, s in ranking[:3]]
                for i, _ in ranking[:5]:
                    attribution.setdefault(i, req)
        fused = rrf(rankings, k=config.get("retrieval.rrf_k", 60)) if len(rankings) > 1 else (rankings[0] if rankings else [])
        if fused:
            top = max(s for _, s in fused) or 1.0
            fused = [(i, s / top) for i, s in fused]
        if opts.outcome:
            boosts = config.get("retrieval.outcome_boost", {})
            fused = sorted(((i, s + self.project_prior.get(chunks[i].project or "", 0.0) * 0.5
                             + boosts.get(chunks[i].meta.get("outcome"), 0.0) * 0.5) for i, s in fused), key=lambda x: -x[1])
        evidence = [Evidence(chunks[i], s, attribution.get(i)) for i, s in fused
                    if not deleted or chunks[i].meta.get("item_id") not in deleted]
        if opts.multivector:
            evidence = _group_projects(evidence)
        return RetrievalResult(evidence[: max(opts.k, 10)], by_req, unsupported, reqs,
                               {"queries": len(queries), "candidates": len(fused)})

    def _grade(self, req: str, ranking: list[tuple[int, float]], chunks: list[Chunk]) -> float:
        """Evidence grade for corrective RAG: best lexical coverage of the (expanded) requirement in the top 3."""
        terms = set(tokenize(expand(req)))
        if not terms or not ranking:
            return 0.0
        best = 0.0
        for i, _ in ranking[:3]:
            c = chunks[i]
            toks = set(tokenize(c.text + " " + " ".join(c.meta.get("skills", []))))
            best = max(best, len(terms & toks) / len(terms))
        return best

    def search(self, requirement: str, k: int = 5, filters: dict | None = None, opts: Options | None = None) -> list[Evidence]:
        opts = replace(opts or Options(hybrid=True, rerank=True), decompose=False, k=k)
        res = self.retrieve({"title": "", "description": requirement}, opts)
        ev = res.evidence
        if filters:
            ev = [e for e in ev if all(_match(e.chunk.meta.get(fk), fv) for fk, fv in filters.items())]
        return ev[:k]


def _match(value: Any, want: Any) -> bool:
    if isinstance(value, list):
        return any(str(want).lower() == str(v).lower() for v in value)
    return str(value).lower() == str(want).lower() if want is not None else True


def _group_projects(evidence: list[Evidence]) -> list[Evidence]:
    """V5: collapse chunks from the same project into one item, scored by its best chunk plus support from others."""
    best: dict[str, Evidence] = {}
    extra: dict[str, float] = defaultdict(float)
    out: list[Evidence] = []
    for e in evidence:
        p = e.chunk.project
        if not p:
            out.append(e)
            continue
        if p not in best:
            best[p] = e
        else:
            extra[p] += 0.15 * e.score
    for p, e in best.items():
        out.append(Evidence(e.chunk, e.score + extra[p], e.requirement, {"grouped": 1.0}))
    return sorted(out, key=lambda x: -x.score)
