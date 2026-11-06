import os

import pytest

os.environ["GIGBID_MCP_INPROCESS"] = "1"


@pytest.fixture(autouse=True)
def gigsim_port():
    from gigsim_standin.app import sim
    from mcp_servers.marketplace import server
    from tests.fakes import gigsim_adapter

    sim.reset()
    server._port_override = gigsim_adapter()
    yield sim
    server._port_override = None


def live_job(sim, kind: str, persona: str = "ai_ml", n: int = 0) -> dict:
    jobs = [j for j in sim.all_jobs if j["_meta"]["persona"] == persona and j["_meta"].get("kind") == kind
            and sim.clients[j["client_id"]].get("payment_verified")]
    return sim.get_job(jobs[n]["id"])


def initial(job: dict, persona: str = "ai_ml", user: str = "u-test") -> dict:
    return {"user_id": user, "persona": persona, "thread_id": f"{user}:{job['id']}", "trace_id": f"t-{job['id']}", "job": job,
            "meta": {"hourly_floor": 45}}
