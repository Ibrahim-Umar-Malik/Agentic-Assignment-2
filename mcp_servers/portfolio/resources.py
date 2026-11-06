"""Resource templates so a host can load full items: portfolio://case/{id}, portfolio://proposal/{id}, portfolio://profile."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from . import backend


def _find(kind: str, id: str) -> str:
    idx = backend.get()
    for cand in (id, f"{idx.corpus_dir.name}:{kind}:{id}"):
        d = idx.by_item.get(cand)
        if d is not None:
            return f"# {d.meta.get('title') or cand}\n\n```json\n{json.dumps({k: v for k, v in d.meta.items()}, default=str)}\n```\n\n{d.text}"
    raise ValueError(f"not found: {kind}/{id}")


def register(mcp: FastMCP) -> None:
    @mcp.resource("portfolio://case/{id}", name="case_study", description="A full case study by id or project slug",
                  mime_type="text/markdown")
    def case(id: str) -> str:
        return _find("case", id)

    @mcp.resource("portfolio://proposal/{id}", name="past_proposal", description="A past proposal with its outcome",
                  mime_type="text/markdown")
    def proposal(id: str) -> str:
        return _find("proposal", id)

    @mcp.resource("portfolio://profile", name="profile", description="Freelancer profile: headline, rates, skills",
                  mime_type="application/json")
    def profile() -> str:
        return json.dumps(backend.get().profile, indent=2)
