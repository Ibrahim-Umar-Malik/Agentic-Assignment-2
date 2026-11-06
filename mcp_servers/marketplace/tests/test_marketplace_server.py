import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

from mcp_servers.marketplace import server
from tests.fakes import DownAdapter, gigsim_adapter


@pytest.fixture(autouse=True)
def port():
    server._port_override = gigsim_adapter()
    yield
    server._port_override = None


async def _job_id(s):
    r = await s.call_tool("search_jobs", {"query": "", "limit": 5})
    assert not r.isError, r.content
    return r.structuredContent["jobs"][0]["id"]


async def test_annotations_are_correct():
    async with connect(server.mcp._mcp_server) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
    for name in ["search_jobs", "get_job", "get_client_history", "get_connects_balance", "list_messages"]:
        assert tools[name].annotations.readOnlyHint is True
    for name in ["create_proposal_draft", "submit_proposal", "send_message"]:
        a = tools[name].annotations
        assert a.readOnlyHint is False and a.idempotentHint is True
        assert "idempotency_key" in tools[name].inputSchema["required"]
        assert tools[name].outputSchema is not None
    assert tools["submit_proposal"].annotations.destructiveHint is True
    assert tools["create_proposal_draft"].annotations.destructiveHint is False


async def test_input_constraints_reject_bad_args():
    async with connect(server.mcp._mcp_server) as s:
        r = await s.call_tool("create_proposal_draft", {"job_id": "x", "cover_letter": "too short", "bid_amount": -5,
                                                        "idempotency_key": "k"})
    assert r.isError


async def test_dry_run_previews_without_sending():
    async with connect(server.mcp._mcp_server) as s:
        jid = await _job_id(s)
        letter = "I built a retrieval assistant that cut review time by 41 percent for a law firm. " * 2
        r = await s.call_tool("create_proposal_draft", {"job_id": jid, "cover_letter": letter, "bid_amount": 500,
                                                        "idempotency_key": "dry-run-0001", "dry_run": True})
        assert r.structuredContent["status"] == "dry_run"
        assert r.structuredContent["preview"]["cover_letter"] == letter
        props = await s.call_tool("list_proposals", {})
        assert props.structuredContent["proposals"] == [] or all(p["job_id"] != jid for p in props.structuredContent["proposals"])


async def test_submit_is_exactly_once_and_spends_connects_once():
    async with connect(server.mcp._mcp_server) as s:
        jid = await _job_id(s)
        letter = "I shipped a LangGraph agent that cut handling time from 9 to 3 minutes for dispatchers. " * 2
        d = await s.call_tool("create_proposal_draft", {"job_id": jid, "cover_letter": letter, "bid_amount": 400,
                                                        "idempotency_key": "draft-key-01"})
        draft_id = d.structuredContent["result"]["id"]
        before = (await s.call_tool("get_connects_balance", {})).structuredContent["connects"]
        preview = await s.call_tool("submit_proposal", {"draft_id": draft_id, "job_id": jid, "idempotency_key": "submit-key-01", "dry_run": True})
        cost = preview.structuredContent["connects_cost"]
        assert preview.structuredContent["connects_balance_after"] == before - cost
        r1 = await s.call_tool("submit_proposal", {"draft_id": draft_id, "job_id": jid, "idempotency_key": "submit-key-01"})
        r2 = await s.call_tool("submit_proposal", {"draft_id": draft_id, "job_id": jid, "idempotency_key": "submit-key-01"})
        after = (await s.call_tool("get_connects_balance", {})).structuredContent["connects"]
    assert r1.structuredContent["status"] == "ok" and r2.structuredContent["status"] == "duplicate"
    assert before - after == cost


async def test_audit_log_is_append_only():
    from sqlalchemy import text

    from core.db import engine

    async with connect(server.mcp._mcp_server) as s:
        await s.call_tool("get_connects_balance", {})
    with engine().begin() as c:
        assert c.execute(text("select count(*) from audit_log")).scalar() > 0
    with pytest.raises(Exception):  # noqa: B017  (driver-specific IntegrityError/OperationalError)
        with engine().begin() as c:
            c.execute(text("delete from audit_log"))


async def test_marketplace_down_is_a_clear_error():
    server._port_override = DownAdapter()
    async with connect(server.mcp._mcp_server) as s:
        r = await s.call_tool("search_jobs", {"query": "x"})
    assert r.isError and "unreachable" in r.content[0].text.lower()


def test_http_endpoint_requires_bearer():
    from starlette.testclient import TestClient

    with TestClient(server.http_app()) as c:
        assert c.post("/mcp", json={}).status_code == 401
