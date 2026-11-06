# gigbid-portfolio-mcp

An MCP server that answers one question well: **"What in my portfolio proves I can do this?"**

Point it at a folder of your work (CV, case studies, repo READMEs and code, client reviews, past proposals with
their outcomes) and any MCP host (Claude Desktop, Cursor, Claude Code, GigBid) can search it for evidence,
requirement by requirement, before writing a proposal or answering a screening question.

It is read-only. It never sends anything anywhere.

## Install and run

No PyPI needed; `uvx` installs it straight from GitHub:

```bash
uvx --from "git+https://github.com/Ibrahim-Umar-Malik/Agentic-Assignment-2#subdirectory=mcp_servers/portfolio" \
    gigbid-portfolio-mcp --corpus ~/my-portfolio
```

Without `--corpus` it serves a bundled sample persona (an AI/ML engineer) so you can try it immediately.

Docker (from the repository root):

```bash
docker build -f mcp_servers/portfolio/Dockerfile -t gigbid-portfolio-mcp .
docker run -i --rm -v ~/my-portfolio:/portfolio -e PORTFOLIO_DIR=/portfolio gigbid-portfolio-mcp
```

Streamable HTTP instead of stdio: add `--http --port 8004`.

### Claude Desktop / Cursor

```json
{
  "mcpServers": {
    "portfolio": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Ibrahim-Umar-Malik/Agentic-Assignment-2#subdirectory=mcp_servers/portfolio",
               "gigbid-portfolio-mcp", "--corpus", "/Users/you/my-portfolio"]
    }
  }
}
```

## What it exposes

| Kind | Name | What it does |
|---|---|---|
| tool | `search_evidence(requirement, k, filters)` | Ranked evidence for one requirement: type, source, date, outcome, snippet. Filters: type, project, outcome, skill, exclude_ids. Returns a "do not claim" note when nothing matches. |
| tool | `get_case_study(id)` | Full item plus related items about the same project (README, code, reviews, proposals). |
| tool | `list_skills()` | Every skill and how many evidence items support it. |
| resource | `portfolio://case/{id}` | A full case study (id or project slug). |
| resource | `portfolio://proposal/{id}` | A past proposal with its outcome. |
| resource | `portfolio://profile` | Headline, rates and skills. |
| prompt | Answer a screening question from my portfolio | Evidence-only answer under 120 words. |
| prompt | Which of my projects prove this requirement? | Two best projects, with numbers quoted exactly. |
| prompt | Draft a specific opening line for a job | Two openings, each citing a real result. |

All tools are annotated `readOnlyHint: true`.

## Portfolio folder format

```
my-portfolio/
  profile.json                 {"name": "...", "headline": "...", "skills": ["..."], "hourly_floor_usd": 40}
  cv.md | cv.pdf
  case_studies/<slug>.md       optional JSON front matter: {"id","project","title","date","skills","client_industry"}
  repos/<slug>/README.md       plus any source files (.py .ts .sql ...); code is indexed separately
  repos/<slug>/meta.json       {"project": "<slug>", "skills": [...]}  (optional)
  reviews.jsonl                {"id","project","rating","text","date"}
  proposals.jsonl              {"id","project","job_title","text","outcome": "won|replied|ignored","date"}
```

## How retrieval works

Structure-aware chunks (sections, code blocks, one record per review or proposal), hybrid BM25 + dense retrieval
with reciprocal rank fusion (so exact names like "Celery" or "dbt" are not blurred by embeddings), reranking,
and an outcome prior that favours evidence from proposals that won or got replies. The default embedder is a
dependency-free hashing embedder; set `GIGBID_EMBEDDER=sentence-transformers:BAAI/bge-small-en-v1.5` and
`GIGBID_RERANKER=cross-encoder:BAAI/bge-reranker-v2-m3` (after `pip install "gigbid-portfolio-mcp[models]"`)
for neural models. The design was chosen by measurement in GigBid's evaluation (see the main repository).

## Tests

`pytest mcp_servers/portfolio/tests` (in-memory MCP client, plus a schema snapshot in `tests/contract`).

MIT licensed. Part of [GigBid](https://github.com/Ibrahim-Umar-Malik/Agentic-Assignment-2).
