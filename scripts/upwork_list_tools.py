"""Print the official Upwork MCP server's real tool list for a user who connected Upwork in Settings, and show
which GigBid port method each tool maps to (mcp_servers/marketplace/adapters/upwork_live.py: TOOL_CANDIDATES).

    python scripts/upwork_list_tools.py <gigbid-user-id>

Read-only: lists tools, never calls them."""

from __future__ import annotations

import asyncio
import sys

from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter, tool_map


async def main(user_id: str) -> None:
    tools = await UpworkLiveAdapter(user_id)._client_tools()
    print(f"{len(tools)} tools on the Upwork MCP server:")
    for name, t in sorted(tools.items()):
        print(f"  {name}: {(t.description or '').splitlines()[0][:100] if t.description else ''}")
    print("\nport method -> mapped tool")
    for method, cands in tool_map().items():
        hit = next((c for c in cands if c in tools), None)
        print(f"  {method:24s} {hit or 'NOT FOUND: set UPWORK_TOOL_MAP'}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1]))
