"""Variant registry. A shipped pipeline may combine variants: "v2_hybrid_v1_decompose_v4_outcome" ORs their options."""

from __future__ import annotations

import importlib
from dataclasses import fields, replace

from ..pipeline import Options

VARIANTS = ["v0_naive", "v1_decompose", "v2_hybrid", "v3_rerank", "v4_outcome", "v5_multivector", "v6_contextual",
            "v7_hyde", "v8_corrective"]


def options_for(spec: str) -> Options:
    """Parse "v2_hybrid" or a combination such as "v2_hybrid_v1_decompose_v4_outcome"."""
    parts = []
    for name in VARIANTS:
        if name in spec:
            parts.append(importlib.import_module(f"{__name__}.{name}").OPTIONS)
    if not parts:
        raise ValueError(f"unknown variant spec {spec}")
    base = parts[0]
    for p in parts[1:]:
        upd = {f.name: getattr(p, f.name) for f in fields(Options)
               if isinstance(getattr(p, f.name), bool) and getattr(p, f.name)}
        if p.chunking == "structured":
            upd["chunking"] = "structured"
        base = replace(base, **upd)
    return base
