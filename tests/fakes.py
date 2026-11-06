"""In-process GigSim-backed adapter used by tests: same port, no network."""

from __future__ import annotations

import httpx

from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter


def gigsim_adapter(token: str = "dev-ai_ml") -> GigSimAdapter:
    from gigsim_standin.app import app

    return GigSimAdapter(token, base_url="http://gigsim", transport=httpx.ASGITransport(app=app), retries=1)


class DownAdapter(GigSimAdapter):
    """Simulates a killed marketplace: every call fails as unreachable."""

    def __init__(self):
        super().__init__("x", base_url="http://127.0.0.1:9", timeout=0.2, retries=0)
