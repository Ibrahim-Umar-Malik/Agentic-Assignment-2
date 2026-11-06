"""R1: the single marketplace port. Every marketplace access goes through this interface; the two adapters
(mcp_servers/marketplace/adapters/gigsim.py and upwork_live.py) are selected by config, per user.

The graph never imports this module directly: agents reach the port only through the Marketplace MCP server's
tools, so the graph cannot tell which marketplace it is using.
"""

from __future__ import annotations

from typing import Any, Protocol


class MarketplaceUnavailable(RuntimeError):
    """Raised for timeouts / 5xx / connection errors after bounded retries; drives the degraded mode."""


class MarketplaceRateLimited(RuntimeError):
    def __init__(self, retry_after: float):
        super().__init__(f"rate limited, retry after {retry_after}s")
        self.retry_after = retry_after


class MarketplacePort(Protocol):
    name: str

    async def search_jobs(self, query: str, category: str | None, skills: list[str] | None, limit: int) -> list[dict[str, Any]]: ...
    async def get_job(self, job_id: str) -> dict[str, Any]: ...
    async def get_client_history(self, client_id: str) -> dict[str, Any]: ...
    async def get_market_stats(self, category: str, budget_type: str) -> dict[str, Any]: ...
    async def get_connects_balance(self) -> dict[str, Any]: ...
    async def list_threads(self) -> list[dict[str, Any]]: ...
    async def list_proposals(self) -> list[dict[str, Any]]: ...
    async def list_events(self, since: int) -> list[dict[str, Any]]: ...
    async def create_proposal_draft(self, job_id: str, cover_letter: str, bid_amount: float, answers: list[str],
                                    idempotency_key: str) -> dict[str, Any]: ...
    async def submit_proposal(self, draft_id: str, idempotency_key: str) -> dict[str, Any]: ...
    async def send_message(self, thread_id: str, body: str, idempotency_key: str) -> dict[str, Any]: ...
    async def policy(self) -> dict[str, Any]: ...


def get_port(user: dict[str, Any]) -> MarketplacePort:
    """Factory: choose the adapter from config (marketplace.mode) and the user's connected account."""
    from core import config

    mode = (user.get("settings") or {}).get("marketplace") or config.get("marketplace.mode", "gigsim")
    if mode == "upwork_live":
        from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter

        return UpworkLiveAdapter(user["id"])
    from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter

    return GigSimAdapter.for_user(user)
