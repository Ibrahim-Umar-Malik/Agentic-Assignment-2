"""GigSim adapter for the marketplace port: REST over httpx with timeouts, bounded retries with backoff,
Retry-After handling for 429s and a typed error for the degraded mode. The only module that knows GigSim's
HTTP shape: if the official simulator's paths differ, change them here and nowhere else."""

from __future__ import annotations

import asyncio
import os
import random
from typing import Any

import httpx

from agent.marketplace_port import MarketplaceRateLimited, MarketplaceUnavailable

GIGSIM_URL = os.environ.get("GIGSIM_URL", "http://localhost:8001")


class GigSimAdapter:
    name = "gigsim"

    def __init__(self, token: str, base_url: str | None = None, timeout: float = 10.0, retries: int = 3,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.token = token
        self.base_url = (base_url or os.environ.get("GIGSIM_URL", GIGSIM_URL)).rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.transport = transport

    @classmethod
    def for_user(cls, user: dict[str, Any]) -> GigSimAdapter:
        settings = user.get("settings") or {}
        token = settings.get("gigsim_token") or f"dev-{user.get('persona') or 'ai_ml'}"
        return cls(token)

    async def _req(self, method: str, path: str, **kw: Any) -> Any:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout, transport=self.transport,
                                             headers={"Authorization": f"Bearer {self.token}"}) as c:
                    r = await c.request(method, path, **kw)
                if r.status_code == 429:
                    ra = float(r.headers.get("Retry-After", "2"))
                    if attempt < self.retries and ra <= 10:
                        await asyncio.sleep(ra)
                        continue
                    raise MarketplaceRateLimited(ra)
                if r.status_code >= 500:
                    last = MarketplaceUnavailable(f"GigSim {r.status_code}")
                elif r.status_code >= 400:
                    raise ValueError(f"GigSim {r.status_code}: {r.text[:200]}")
                else:
                    return r.json()
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last = MarketplaceUnavailable(f"GigSim unreachable: {type(e).__name__}")
            await asyncio.sleep(min(8.0, 0.4 * 2**attempt) * (0.75 + random.random() / 2))
        raise last or MarketplaceUnavailable("GigSim failed")

    async def search_jobs(self, query: str = "", category: str | None = None, skills: list[str] | None = None, limit: int = 20):
        params: dict[str, Any] = {"q": query, "limit": limit}
        if category:
            params["category"] = category
        if skills:
            params["skills"] = ",".join(skills)
        return (await self._req("GET", "/v1/jobs", params=params))["jobs"]

    async def get_job(self, job_id: str):
        return await self._req("GET", f"/v1/jobs/{job_id}")

    async def get_client_history(self, client_id: str):
        return await self._req("GET", f"/v1/clients/{client_id}")

    async def get_market_stats(self, category: str, budget_type: str):
        return await self._req("GET", "/v1/stats", params={"category": category, "budget_type": budget_type})

    async def get_connects_balance(self):
        return await self._req("GET", "/v1/connects")

    async def list_threads(self):
        return (await self._req("GET", "/v1/threads"))["threads"]

    async def list_proposals(self):
        return (await self._req("GET", "/v1/proposals"))["proposals"]

    async def list_events(self, since: int = 0):
        return (await self._req("GET", "/v1/events", params={"since": since}))["events"]

    async def create_proposal_draft(self, job_id, cover_letter, bid_amount, answers, idempotency_key):
        return await self._req("POST", "/v1/proposals/drafts", json={"job_id": job_id, "cover_letter": cover_letter,
                                                                       "bid_amount": bid_amount, "answers": answers,
                                                                       "idempotency_key": idempotency_key})

    async def submit_proposal(self, draft_id, idempotency_key):
        return await self._req("POST", f"/v1/proposals/drafts/{draft_id}/submit", json={"idempotency_key": idempotency_key})

    async def send_message(self, thread_id, body, idempotency_key):
        return await self._req("POST", f"/v1/threads/{thread_id}/messages", json={"body": body, "idempotency_key": idempotency_key})

    async def policy(self):
        return await self._req("GET", "/v1/policy")
