"""GitHub ingestion through the official GitHub MCP server (third-party server, A5 / B1).

Uses MultiServerMCPClient over Streamable HTTP to https://api.githubcopilot.com/mcp/ with a read-only fine-grained
token (GITHUB_MCP_TOKEN). Only the `get_file_contents` / `search_repositories` read tools are allowed
(see agent/mcp_client.py allowlists). Each repo becomes repos/<name>/README.md + selected source files +
meta.json in the user's portfolio folder, then the index is rebuilt incrementally.

CLI: python -m rag.ingest.github --owner <github-user> --repos repo1,repo2 --out var/portfolio/<user_id>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

GITHUB_MCP_URL = os.environ.get("GITHUB_MCP_URL", "https://api.githubcopilot.com/mcp/")
CODE_EXT = (".py", ".ts", ".tsx", ".js", ".sql", ".go", ".ipynb")
ALLOWED = {"get_file_contents", "search_repositories", "list_commits"}


async def _tools() -> dict[str, Any]:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    token = os.environ.get("GITHUB_MCP_TOKEN")
    if not token:
        raise RuntimeError("Set GITHUB_MCP_TOKEN (a read-only fine-grained GitHub token)")
    client = MultiServerMCPClient({"github": {"transport": "streamable_http", "url": GITHUB_MCP_URL,
                                              "headers": {"Authorization": f"Bearer {token}"}}})
    return {t.name: t for t in await client.get_tools() if t.name in ALLOWED}


def _text(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        return "\n".join(_text(r) for r in result)
    if isinstance(result, dict):
        return result.get("text") or result.get("content") or json.dumps(result)
    return str(result)


async def ingest_repo(owner: str, repo: str, out: Path, max_files: int = 6) -> Path:
    tools = await _tools()
    get = tools["get_file_contents"]
    rdir = out / "repos" / repo
    rdir.mkdir(parents=True, exist_ok=True)
    try:
        readme = _text(await get.ainvoke({"owner": owner, "repo": repo, "path": "README.md"}))
    except Exception:
        readme = f"# {repo}\n"
    (rdir / "README.md").write_text(readme)
    listing = _text(await get.ainvoke({"owner": owner, "repo": repo, "path": "/"}))
    paths = [p for p in json.loads(listing) if isinstance(p, dict) and p.get("path", "").endswith(CODE_EXT)] \
        if listing.strip().startswith("[") else []
    for p in paths[:max_files]:
        code = _text(await get.ainvoke({"owner": owner, "repo": repo, "path": p["path"]}))
        dest = rdir / p["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(code[:20000])
    (rdir / "meta.json").write_text(json.dumps({"id": f"github:{owner}/{repo}", "project": repo, "skills": []}))
    return rdir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True)
    ap.add_argument("--repos", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    for r in a.repos.split(","):
        print("ingested", asyncio.run(ingest_repo(a.owner, r.strip(), Path(a.out))))


if __name__ == "__main__":
    main()
