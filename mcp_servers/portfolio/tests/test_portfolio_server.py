from mcp.shared.memory import create_connected_server_and_client_session as connect

from mcp_servers.portfolio.server import mcp


async def test_tools_resources_prompts_listed():
    async with connect(mcp._mcp_server) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
        templates = {t.uriTemplate for t in (await s.list_resource_templates()).resourceTemplates}
        prompts = {p.name for p in (await s.list_prompts()).prompts}
    assert set(tools) == {"search_evidence", "get_case_study", "list_skills"}
    assert all(t.annotations.readOnlyHint for t in tools.values())
    assert {"portfolio://case/{id}", "portfolio://proposal/{id}"} <= templates
    assert "answer_screening_question" in prompts


async def test_search_finds_skill_only_present_in_code():
    # "Celery" never appears in the support-bot case study, only in its repo code
    async with connect(mcp._mcp_server) as s:
        r = await s.call_tool("search_evidence", {"requirement": "Celery task queue", "k": 5, "portfolio_id": "ai_ml"})
    items = r.structuredContent["items"]
    assert any(i["type"] == "repo_code" for i in items)


async def test_search_returns_outcome_for_proposals_and_respects_filters():
    async with connect(mcp._mcp_server) as s:
        r = await s.call_tool("search_evidence", {"requirement": "LangGraph agent", "k": 3, "portfolio_id": "ai_ml",
                                                  "filters": {"type": "proposal", "outcome": "won"}})
    for i in r.structuredContent["items"]:
        assert i["type"] == "proposal" and i["outcome"] == "won"


async def test_excluded_evidence_is_not_returned():
    async with connect(mcp._mcp_server) as s:
        r1 = await s.call_tool("search_evidence", {"requirement": "contract clause RAG", "k": 1, "portfolio_id": "ai_ml"})
        top = r1.structuredContent["items"][0]["id"]
        r2 = await s.call_tool("search_evidence", {"requirement": "contract clause RAG", "k": 5, "portfolio_id": "ai_ml",
                                                   "filters": {"exclude_ids": [top]}})
    assert top not in [i["id"] for i in r2.structuredContent["items"]]


async def test_case_study_resource_and_tool():
    async with connect(mcp._mcp_server) as s:
        res = await s.read_resource("portfolio://case/legal-rag")
        cs = await s.call_tool("get_case_study", {"id": "ai_ml:case:legal-rag", "portfolio_id": "ai_ml"})
    assert "law firm" in res.contents[0].text
    assert cs.structuredContent["project"] == "legal-rag" and cs.structuredContent["related"]
