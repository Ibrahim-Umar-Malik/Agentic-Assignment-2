"""Live Upwork adapter for the marketplace port (A4).

Connects to Upwork's official MCP server (https://mcp.upwork.com/mcp) through MultiServerMCPClient over
Streamable HTTP, with the user's OAuth 2.1 access token (obtained by apps/api/auth/upwork_oauth.py and stored
encrypted per user). Upwork's tool names are mapped onto the port by `TOOL_CANDIDATES`; run
`python scripts/upwork_list_tools.py` after connecting to print the server's real tool list and adjust the
mapping (or set UPWORK_TOOL_MAP as JSON) without touching the graph.

Rules enforced here, whatever the caller asks:
  * reads only; the worker schedules them no more often than scheduling.live_scout_interval_min;
  * writes create DRAFTS on Upwork; the freelancer confirms them on Upwork. `submit_proposal` never submits;
  * no browser automation, no cookies, no scraping: the MCP server is the only channel.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from agent.marketplace_port import MarketplaceUnavailable
from core.crypto import load_oauth_tokens

UPWORK_MCP_URL = os.environ.get("UPWORK_MCP_URL", "https://mcp.upwork.com/mcp")

# port method -> candidate Upwork MCP tool names (first one the server exposes wins)
TOOL_CANDIDATES: dict[str, list[str]] = {
    "search_jobs": ["search_jobs", "job_search", "searchJobs", "find_jobs"],
    "get_job": ["get_job", "get_job_details", "getJob", "job_details"],
    "get_client_history": ["get_client", "get_client_info", "client_details"],
    "list_threads": ["list_rooms", "list_messages", "get_messages", "list_conversations"],
    "list_proposals": ["list_proposals", "get_proposals", "my_proposals"],
    "create_proposal_draft": ["create_proposal_draft", "draft_proposal", "create_proposal"],
    "send_message": ["create_message_draft", "draft_message", "send_message"],
    "get_connects_balance": ["get_connects", "connects_balance", "get_profile"],
}


def tool_map() -> dict[str, list[str]]:
    m = dict(TOOL_CANDIDATES)
    if os.environ.get("UPWORK_TOOL_MAP"):
        m.update({k: [v] if isinstance(v, str) else v for k, v in json.loads(os.environ["UPWORK_TOOL_MAP"]).items()})
    return m


class UpworkLiveAdapter:
    name = "upwork_live"

    def __init__(self, user_id: str):
        self.user_id = user_id
        self._tools: dict[str, Any] | None = None

    async def _client_tools(self) -> dict[str, Any]:
        if self._tools is not None:
            return self._tools
        tokens = load_oauth_tokens(self.user_id, "upwork")
        if not tokens:
            raise MarketplaceUnavailable("Upwork account not connected")
        if tokens.get("expires_at") and tokens["expires_at"] < time.time() + 60:
            from apps.api.auth.upwork_oauth import refresh

            tokens = await refresh(self.user_id, tokens)
        from langchain_mcp_adapters.client import MultiServerMCPClient

        client = MultiServerMCPClient({"upwork": {"transport": "streamable_http", "url": UPWORK_MCP_URL,
                                                  "headers": {"Authorization": f"Bearer {tokens['access_token']}"}}})
        try:
            tools = await client.get_tools()
        except Exception as e:
            raise MarketplaceUnavailable(f"Upwork MCP unavailable: {type(e).__name__}")
        self._tools = {t.name: t for t in tools}
        return self._tools

    async def _call(self, method: str, **args: Any) -> Any:
        tools = await self._client_tools()
        for name in tool_map().get(method, []):
            if name in tools:
                try:
                    out = await tools[name].ainvoke(args)
                except Exception as e:
                    raise MarketplaceUnavailable(f"Upwork tool {name} failed: {type(e).__name__}")
                if isinstance(out, str):
                    try:
                        return json.loads(out)
                    except json.JSONDecodeError:
                        return {"text": out}
                return out
        raise NotImplementedError(f"Upwork MCP exposes no tool for {method}; set UPWORK_TOOL_MAP")

    async def search_jobs(self, query: str = "", category=None, skills=None, limit: int = 20):
        res = await self._call("search_jobs", query=" ".join([query] + (skills or [])).strip(), limit=limit)
        jobs = res.get("jobs", res) if isinstance(res, dict) else res
        return [_normalise_job(j) for j in (jobs or [])]

    async def get_job(self, job_id: str):
        return _normalise_job(await self._call("get_job", job_id=job_id))

    async def get_client_history(self, client_id: str):
        try:
            return await self._call("get_client_history", client_id=client_id)
        except NotImplementedError:
            return {"id": client_id, "note": "client history not exposed by Upwork MCP; risk uses job-level client fields"}

    async def get_market_stats(self, category: str, budget_type: str):
        # Upwork exposes no market statistics tool; pricing falls back to the user's floor and the job budget.
        return {"category": category, "n": 0, "source": "unavailable_live"}

    async def get_connects_balance(self):
        try:
            return await self._call("get_connects_balance")
        except NotImplementedError:
            return {"connects": None, "note": "balance not exposed; Connects are confirmed on Upwork"}

    async def list_threads(self):
        res = await self._call("list_threads")
        return res.get("threads", res) if isinstance(res, dict) else res

    async def list_proposals(self):
        res = await self._call("list_proposals")
        return res.get("proposals", res) if isinstance(res, dict) else res

    async def list_events(self, since: int = 0):
        return []  # live mode derives pipeline changes from list_proposals / list_threads on the scout schedule

    async def create_proposal_draft(self, job_id, cover_letter, bid_amount, answers, idempotency_key):
        res = await self._call("create_proposal_draft", job_id=job_id, cover_letter=cover_letter, bid_amount=bid_amount,
                               answers=answers)
        return {"id": (res or {}).get("id", idempotency_key), "status": "draft_on_upwork", "raw": res}

    async def submit_proposal(self, draft_id, idempotency_key):
        # Never submits: Upwork requires the freelancer to confirm the draft on Upwork itself.
        return {"id": draft_id, "status": "awaiting_confirmation_on_upwork",
                "note": "Open Upwork and confirm this draft to submit it."}

    async def send_message(self, thread_id, body, idempotency_key):
        res = await self._call("send_message", room_id=thread_id, message=body)
        return {"id": (res or {}).get("id", idempotency_key), "status": "draft_on_upwork", "raw": res}

    async def policy(self):
        return {"version": "upwork", "description": "Upwork Terms of Service; every write is a draft the user confirms."}


def _normalise_job(j: Any) -> dict:
    if not isinstance(j, dict):
        return {"id": str(j), "title": str(j), "description": ""}
    budget = j.get("budget") or j.get("amount") or j.get("hourlyBudgetMax") or 0
    if isinstance(budget, dict):
        budget = budget.get("amount") or budget.get("max") or 0
    return {"id": str(j.get("id") or j.get("ciphertext") or j.get("job_id")), "title": j.get("title", ""),
            "description": j.get("description") or j.get("snippet", ""), "skills": [s if isinstance(s, str) else s.get("name", "")
                                                                                 for s in j.get("skills", [])],
            "category": j.get("category") or "unknown", "budget_type": "hourly" if j.get("hourly") or j.get("hourlyBudgetMax") else "fixed",
            "budget": float(budget or 0), "client_id": str((j.get("client") or {}).get("id", j.get("client_id", ""))),
            "client": j.get("client"), "connects_cost": j.get("connectsRequired") or j.get("connects_cost") or 0,
            "screening_questions": j.get("questions") or j.get("screening_questions") or [], "posted_at": j.get("createdDateTime")}
