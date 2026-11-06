"""Schema snapshot test (A7): fails CI when a tool signature changes unintentionally.
Intentional change: UPDATE_SNAPSHOTS=1 pytest tests/contract && commit the new snapshot."""

import json
import os
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

from mcp_servers.marketplace.server import mcp as marketplace
from mcp_servers.portfolio.server import mcp as portfolio
from mcp_servers.workspace.server import mcp as workspace

SNAP = Path(__file__).parent / "snapshots"


@pytest.mark.parametrize("name,server", [("portfolio", portfolio), ("marketplace", marketplace), ("workspace", workspace)])
async def test_tool_schemas_match_snapshot(name, server):
    async with connect(server._mcp_server) as s:
        tools = (await s.list_tools()).tools
    current = {t.name: {"input": t.inputSchema, "output": t.outputSchema,
                        "annotations": t.annotations.model_dump(exclude_none=True) if t.annotations else None}
               for t in sorted(tools, key=lambda t: t.name)}
    path = SNAP / f"{name}.json"
    if os.environ.get("UPDATE_SNAPSHOTS") == "1" or not path.exists():
        path.write_text(json.dumps(current, indent=1, sort_keys=True))
    assert json.loads(path.read_text()) == json.loads(json.dumps(current)), f"{name} tool schema changed; see docstring"
