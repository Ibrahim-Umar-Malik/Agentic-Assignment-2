from mcp.shared.memory import create_connected_server_and_client_session as connect

from mcp_servers.workspace.server import mcp


async def test_slots_hold_and_draft():
    async with connect(mcp._mcp_server) as s:
        slots = (await s.call_tool("free_slots", {"days": 5, "duration_min": 30})).structuredContent["slots"]
        assert slots
        h1 = await s.call_tool("create_interview_hold", {"start": slots[0]["start"], "end": slots[0]["end"], "title": "Interview: job 1"})
        h2 = await s.call_tool("create_interview_hold", {"start": slots[0]["start"], "end": slots[0]["end"], "title": "Interview: job 1"})
        assert h1.structuredContent["id"] == h2.structuredContent["id"]  # idempotent
        slots2 = (await s.call_tool("free_slots", {"days": 5, "duration_min": 30})).structuredContent["slots"]
        assert slots[0] not in slots2  # held slot is no longer free
        d = await s.call_tool("create_email_draft", {"to": "client@example.com", "subject": "Interview", "body": "Hi"})
        assert d.structuredContent["status"] == "draft"
