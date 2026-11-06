# Portfolio MCP server as a container (build context: repository root)
#   docker build -f mcp_servers/portfolio/Dockerfile -t gigbid-portfolio-mcp .
#   docker run -i --rm -v ~/my-portfolio:/portfolio -e PORTFOLIO_DIR=/portfolio gigbid-portfolio-mcp
FROM python:3.12-slim
WORKDIR /src
COPY rag ./rag
COPY data/personas/ai_ml ./data/personas/ai_ml
COPY mcp_servers/portfolio ./mcp_servers/portfolio
RUN pip install --no-cache-dir ./mcp_servers/portfolio
ENTRYPOINT ["gigbid-portfolio-mcp"]
