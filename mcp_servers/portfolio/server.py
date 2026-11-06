"""GigBid Portfolio MCP server (A1): read-only evidence search over a freelancer portfolio.

Standalone:  uvx --from "git+https://github.com/Ibrahim-Umar-Malik/Agentic-Assignment-2#subdirectory=mcp_servers/portfolio" \
             gigbid-portfolio-mcp --corpus ~/my-portfolio
In GigBid:   python -m mcp_servers.portfolio.server --http --port 8004
"""

from __future__ import annotations

import argparse
import os

from mcp.server.fastmcp import FastMCP

from . import prompts, resources, tools

mcp = FastMCP("gigbid-portfolio", instructions=(
    "Evidence from the freelancer's portfolio: case studies, repos, reviews and past proposals with outcomes. "
    "Use search_evidence once per requirement; only claim what the returned evidence supports."),
    stateless_http=True, json_response=True)
tools.register(mcp)
resources.register(mcp)
prompts.register(mcp)


def http_app():
    app = mcp.streamable_http_app()
    secret_required = os.environ.get("PORTFOLIO_REQUIRE_AUTH", "1") == "1" and os.environ.get("GIGBID_ENV") == "production"
    if not secret_required:
        return app
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    try:
        from core import service_auth
    except ImportError:  # standalone: no GigBid auth
        return app

    class Bearer(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if not service_auth.verify(request.headers.get("authorization", "").removeprefix("Bearer ").strip()):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    app.add_middleware(Bearer)
    return app


def main() -> None:
    ap = argparse.ArgumentParser(description="GigBid Portfolio MCP server")
    ap.add_argument("--corpus", help="Portfolio folder (GigBid portfolio format). Defaults to PORTFOLIO_DIR or the bundled sample.")
    ap.add_argument("--http", action="store_true", help="Serve Streamable HTTP instead of stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORTFOLIO_MCP_PORT", "8004")))
    a = ap.parse_args()
    if a.corpus:
        os.environ["PORTFOLIO_DIR"] = a.corpus
    if a.http:
        import uvicorn

        uvicorn.run(http_app(), host=a.host, port=a.port, log_level="warning")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
