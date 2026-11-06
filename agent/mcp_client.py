"""MultiServerMCPClient setup, per-agent tool allowlists, timeouts, bounded retries and the degraded mode (A6).

Agents never call GigSim, Upwork, a database or a file directly: they call `gateway.call(agent, tool, args)`.
* Each agent gets only the tools it needs (ALLOWLIST); anything else raises ToolNotAllowed.
* Every call has a timeout and bounded retries with exponential backoff.
* When a server is unreachable, the gateway marks it down in the health table, the UI shows a banner, the
  worker re-queues the job (status `waiting_marketplace`) and the scheduler retries it when the server is back.

Transport: Streamable HTTP through langchain-mcp-adapters' MultiServerMCPClient (deployment, docker compose), or
in-memory sessions to the same FastMCP server objects (GIGBID_MCP_INPROCESS=1: tests, evals, single process).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from core import service_auth, tracing
from core.db import engine, kv

ALLOWLIST: dict[str, dict[str, list[str]]] = {
    "scout": {"marketplace": ["search_jobs", "get_job", "list_events"]},
    "analyst": {},
    "risk": {"marketplace": ["get_client_history", "get_job"]},
    "matcher": {"portfolio": ["search_evidence", "get_case_study", "list_skills"]},
    "pricing": {"marketplace": ["get_market_stats", "get_connects_balance", "get_policy"]},
    "writer": {"portfolio": ["search_evidence", "get_case_study"]},
    "verifier": {"portfolio": ["search_evidence", "get_case_study", "list_skills"]},
    "critic": {"portfolio": ["search_evidence"]},
    "compliance": {},
    "liaison": {"marketplace": ["list_messages", "get_job"], "portfolio": ["search_evidence"],
                "workspace": ["free_slots", "create_interview_hold", "create_email_draft"]},
    # R&D Question C baselines (read-only tools; evals/runners/architecture_compare.py)
    "single_agent": {"marketplace": ["get_job", "get_client_history", "get_market_stats", "get_connects_balance"],
                     "portfolio": ["search_evidence", "get_case_study", "list_skills"]},
    # Not an agent: the approval executor, which runs only after a human approved (R4). Holds the write tools.
    "executor": {"marketplace": ["create_proposal_draft", "submit_proposal", "send_message", "get_connects_balance"]},
    # Pipeline sync (worker) reads events and proposals to keep the board current.
    "sync": {"marketplace": ["list_events", "list_proposals", "list_messages"]},
}

SERVER_URLS = {
    "marketplace": os.environ.get("MARKETPLACE_MCP_URL", "http://localhost:8002/mcp"),
    "workspace": os.environ.get("WORKSPACE_MCP_URL", "http://localhost:8003/mcp"),
    "portfolio": os.environ.get("PORTFOLIO_MCP_URL", "http://localhost:8004/mcp"),
}


class ToolNotAllowed(PermissionError):
    pass


class ToolUnavailable(RuntimeError):
    def __init__(self, server: str, detail: str):
        super().__init__(f"{server} unavailable: {detail}")
        self.server = server


class ToolFailed(RuntimeError):
    pass


def set_health(server: str, ok: bool, detail: str = "") -> None:
    key = f"health:{server}"
    try:
        with engine().begin() as c:
            c.execute(kv.delete().where(kv.c.key == key))
            c.execute(kv.insert().values(key=key, value={"ok": ok, "detail": detail[:300], "ts": time.time()}))
    except Exception:
        pass


def get_health() -> dict[str, Any]:
    from sqlalchemy import select

    out = {}
    with engine().begin() as c:
        for k, v in c.execute(select(kv.c.key, kv.c.value).where(kv.c.key.like("health:%"))):
            out[k.split(":", 1)[1]] = v
    return out


def _inprocess() -> bool:
    return os.environ.get("GIGBID_MCP_INPROCESS", "0") == "1"


def _server_obj(server: str):
    if server == "marketplace":
        from mcp_servers.marketplace.server import mcp
    elif server == "workspace":
        from mcp_servers.workspace.server import mcp
    else:
        from mcp_servers.portfolio.server import mcp
    return mcp


class ToolGateway:
    def __init__(self, user_id: str, timeout_s: float = 25.0, retries: int = 2):
        self.user_id = user_id
        self.timeout_s = timeout_s
        self.retries = retries

    def allowed(self, agent: str, server: str, tool: str) -> bool:
        return tool in ALLOWLIST.get(agent, {}).get(server, [])

    async def call(self, agent: str, server: str, tool: str, args: dict[str, Any]) -> Any:
        if not self.allowed(agent, server, tool):
            raise ToolNotAllowed(f"agent '{agent}' may not call {server}.{tool}")
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            t0 = time.time()
            try:
                result = await asyncio.wait_for(self._call_once(server, tool, args), timeout=self.timeout_s)
                set_health(server, True)
                tracing.record(f"tool.{server}.{tool}", "tool", agent=agent, args=args, latency_s=round(time.time() - t0, 3),
                               attempt=attempt)
                return result
            except ToolFailed as e:
                msg = str(e).lower()
                if "unreachable" in msg or "unavailable" in msg or "rate limited" in msg:
                    last = ToolUnavailable(server, str(e))
                else:
                    tracing.record(f"tool.{server}.{tool}.error", "tool", agent=agent, error=str(e)[:300])
                    raise
            except (TimeoutError, OSError, ConnectionError) as e:
                last = ToolUnavailable(server, type(e).__name__)
            except Exception as e:  # transport errors from the MCP client (ExceptionGroup, httpx errors)
                last = ToolUnavailable(server, f"{type(e).__name__}: {str(e)[:120]}")
            tracing.record(f"tool.{server}.{tool}.retry", "tool", agent=agent, attempt=attempt, error=str(last)[:200])
            await asyncio.sleep(min(6.0, 0.5 * 2**attempt))
        set_health(server, False, str(last))
        raise last if last else ToolUnavailable(server, "unknown")

    async def _call_once(self, server: str, tool: str, args: dict[str, Any]) -> Any:
        if _inprocess():
            from mcp.shared.memory import create_connected_server_and_client_session

            token = service_auth.inprocess_user.set(self.user_id)
            try:
                async with create_connected_server_and_client_session(_server_obj(server)._mcp_server) as s:
                    r = await s.call_tool(tool, args)
            finally:
                service_auth.inprocess_user.reset(token)
        else:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            client = MultiServerMCPClient({server: {
                "transport": "streamable_http", "url": SERVER_URLS[server],
                "headers": {"Authorization": f"Bearer {service_auth.issue(self.user_id)}",
                            tracing.TRACE_HEADER: tracing.current_trace_id()}}})
            async with client.session(server) as s:
                r = await s.call_tool(tool, args)
        if r.isError:
            raise ToolFailed(" ".join(getattr(c, "text", "") for c in r.content))
        if r.structuredContent is not None:
            sc = r.structuredContent
            return sc.get("result", sc) if set(sc) == {"result"} else sc
        text = " ".join(getattr(c, "text", "") for c in r.content)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    async def langchain_tools(self, agent: str) -> list:
        """LangChain tools for an agent, filtered by its allowlist (used by the ReAct / supervisor baselines and
        the single-agent drafting demo). Each tool routes through `call`, so the same limits apply."""
        from langchain_core.tools import StructuredTool

        tools = []
        for server, names in ALLOWLIST.get(agent, {}).items():
            schemas = await self._schemas(server)
            for name in names:
                if name not in schemas:
                    continue
                desc, schema = schemas[name]

                async def _run(_server=server, _name=name, **kwargs):
                    return json.dumps(await self.call(agent, _server, _name, kwargs), default=str)[:6000]

                tools.append(StructuredTool.from_function(coroutine=_run, name=name, description=desc, args_schema=schema))
        return tools

    async def _schemas(self, server: str) -> dict[str, tuple[str, dict]]:
        from mcp.shared.memory import create_connected_server_and_client_session

        token = service_auth.inprocess_user.set(self.user_id)
        try:
            async with create_connected_server_and_client_session(_server_obj(server)._mcp_server) as s:
                tools = (await s.list_tools()).tools
        finally:
            service_auth.inprocess_user.reset(token)
        return {t.name: (t.description or t.name, t.inputSchema) for t in tools}
