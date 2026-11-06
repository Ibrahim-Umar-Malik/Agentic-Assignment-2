"""Stand-in GigSim REST API: bearer tokens, per-token rate limits (429 + Retry-After) and occasional 5xx."""

from __future__ import annotations

import os
import random
import time
from collections import defaultdict, deque

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .sim import Simulator

RATE_LIMIT_PER_MIN = int(os.environ.get("GIGSIM_RATE_LIMIT_PER_MIN", "120"))


def _tokens() -> dict[str, str]:
    # "token:freelancer,token2:freelancer2". Defaults are dev-only tokens for the three personas.
    raw = os.environ.get("GIGSIM_TOKENS", "dev-ai_ml:f-ai_ml,dev-fullstack:f-fullstack,dev-data_analyst:f-data_analyst")
    return dict(pair.split(":", 1) for pair in raw.split(",") if ":" in pair)


app = FastAPI(title="GigSim (stand-in)", version="1.0.0")
sim = Simulator()
_calls: dict[str, deque] = defaultdict(deque)
_rng = random.Random()


@app.middleware("http")
async def chaos_and_limits(request: Request, call_next):
    if request.url.path.startswith("/v1/") and not request.url.path.startswith("/v1/admin"):
        tok = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        q = _calls[tok]
        now = time.time()
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= RATE_LIMIT_PER_MIN:
            return JSONResponse({"error": "rate_limited"}, status_code=429, headers={"Retry-After": str(int(60 - (now - q[0])) + 1)})
        q.append(now)
        if sim.error_rate and _rng.random() < sim.error_rate:
            return JSONResponse({"error": "upstream_unavailable"}, status_code=503)
    return await call_next(request)


def freelancer(authorization: str = Header(default="")) -> str:
    tok = authorization.removeprefix("Bearer ").strip()
    f = _tokens().get(tok)
    if not f:
        raise HTTPException(401, "invalid token")
    return f


class DraftIn(BaseModel):
    job_id: str
    cover_letter: str = Field(max_length=5000)
    bid_amount: float = Field(gt=0)
    answers: list[str] = []
    idempotency_key: str | None = None


class SubmitIn(BaseModel):
    idempotency_key: str | None = None


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    idempotency_key: str | None = None


@app.get("/health")
def health():
    return {"ok": True, "policy": sim.policy}


@app.get("/v1/policy")
def policy(f: str = Depends(freelancer)):
    return sim.policy


@app.get("/v1/jobs")
def search_jobs(q: str = "", category: str | None = None, skills: str | None = None, limit: int = 50, offset: int = 0,
                f: str = Depends(freelancer)):
    return {"jobs": sim.search_jobs(q, category, skills.split(",") if skills else None, min(limit, 100), offset)}


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str, f: str = Depends(freelancer)):
    j = sim.get_job(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    return j


@app.get("/v1/clients/{client_id}")
def client(client_id: str, f: str = Depends(freelancer)):
    c = sim.client_history(client_id)
    if not c:
        raise HTTPException(404, "client not found")
    return c


@app.get("/v1/stats")
def stats(category: str, budget_type: str = "fixed", f: str = Depends(freelancer)):
    return sim.market_stats(category, budget_type)


@app.get("/v1/connects")
def connects(f: str = Depends(freelancer)):
    return sim.account(f)


@app.post("/v1/proposals/drafts")
def create_draft(body: DraftIn, f: str = Depends(freelancer)):
    try:
        return sim.create_draft(f, body.job_id, body.cover_letter, body.bid_amount, body.answers, body.idempotency_key)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.post("/v1/proposals/drafts/{draft_id}/submit")
def submit(draft_id: str, body: SubmitIn, f: str = Depends(freelancer)):
    try:
        return sim.submit(f, draft_id, body.idempotency_key)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/v1/proposals")
def proposals(f: str = Depends(freelancer)):
    return {"proposals": sim.list_proposals(f)}


@app.get("/v1/threads")
def threads(f: str = Depends(freelancer)):
    return {"threads": sim.list_threads(f)}


@app.post("/v1/threads/{thread_id}/messages")
def send(thread_id: str, body: MessageIn, f: str = Depends(freelancer)):
    try:
        return sim.send_message(f, thread_id, body.body, body.idempotency_key)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/v1/events")
def events(since: int = 0, f: str = Depends(freelancer)):
    return {"events": sim.events(f, since)}


# ---- admin endpoints used by demos, evals and tests (no auth on purpose: bind GigSim to the private network) ----
@app.post("/v1/admin/tick")
def tick():
    return sim.tick()


@app.post("/v1/admin/release")
def release(n: int = 10):
    sim.state["released"] += n
    return {"released": sim.state["released"]}


@app.post("/v1/admin/reset")
def reset():
    sim.reset()
    return {"ok": True}
