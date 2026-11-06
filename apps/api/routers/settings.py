from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update

from agent.mcp_client import get_health
from agent.memory.store import list_memory
from core import config, llm
from core.crypto import load_oauth_tokens
from core.db import engine, row_dict, saved_searches, users
from rag import retriever

from .. import dispatch
from ..auth import upwork_oauth
from ..auth.users import current_user
from ..schemas.models import HealthOut, MemoryItem, PortfolioItem, SearchIn, SearchOut, SettingsIn, UserOut

router = APIRouter(prefix="/api", tags=["settings"])

DEFAULT_SEARCHES = {"ai_ml": ["LLM", "machine learning", "computer vision"], "fullstack": ["React", "Next.js", "Django"],
                    "data_analyst": ["SQL", "Power BI", "dashboard"]}


def seed_searches(user: dict) -> None:
    with engine().begin() as c:
        if c.execute(select(saved_searches).where(saved_searches.c.user_id == user["id"])).first():
            return
        for q in DEFAULT_SEARCHES.get(user.get("persona") or "ai_ml", []):
            c.execute(saved_searches.insert().values(id=uuid.uuid4().hex[:10], user_id=user["id"], query=q, interval_min=30, last_run=0))


@router.get("/settings", response_model=UserOut)
def get_settings(user: dict = Depends(current_user)):
    return UserOut(id=user["id"], email=user["email"], name=user.get("name"), persona=user.get("persona"), settings=user.get("settings") or {})


@router.put("/settings", response_model=UserOut)
def put_settings(body: SettingsIn, user: dict = Depends(current_user)):
    s = dict(user.get("settings") or {})
    upd = body.model_dump(exclude_none=True)
    persona = upd.pop("persona", None)
    if upd.get("marketplace") == "upwork_live" and not load_oauth_tokens(user["id"], "upwork"):
        raise HTTPException(409, "connect your Upwork account first")
    s.update(upd)
    with engine().begin() as c:
        c.execute(update(users).where(users.c.id == user["id"]).values(settings=s, **({"persona": persona} if persona else {})))
    return get_settings({**user, "settings": s, "persona": persona or user.get("persona")})


@router.get("/searches", response_model=list[SearchOut])
def searches(user: dict = Depends(current_user)):
    with engine().begin() as c:
        return [SearchOut(**row_dict(r)) for r in c.execute(select(saved_searches).where(saved_searches.c.user_id == user["id"]))]


@router.post("/searches", response_model=SearchOut)
def add_search(body: SearchIn, user: dict = Depends(current_user)):
    sid = uuid.uuid4().hex[:10]
    with engine().begin() as c:
        c.execute(saved_searches.insert().values(id=sid, user_id=user["id"], last_run=0, **body.model_dump()))
    return SearchOut(id=sid, **body.model_dump())


@router.delete("/searches/{sid}")
def del_search(sid: str, user: dict = Depends(current_user)) -> dict:
    with engine().begin() as c:
        c.execute(saved_searches.delete().where(saved_searches.c.id == sid, saved_searches.c.user_id == user["id"]))
    return {"ok": True}


# ---------------- portfolio
def _udir(user: dict) -> Path:
    return retriever.USER_DIR / user["id"]


@router.get("/portfolio", response_model=list[PortfolioItem])
def portfolio(user: dict = Depends(current_user)):
    idx = retriever.get_index(user.get("persona") or "ai_ml", user["id"])
    deleted = set((user.get("settings") or {}).get("deleted_items", []))
    seen, out = set(), []
    for d in idx.docs:
        iid = d.meta.get("item_id") or d.id
        if iid in seen:
            continue
        seen.add(iid)
        out.append(PortfolioItem(id=iid, type=d.meta.get("type"), title=d.meta.get("title"), project=d.meta.get("project"),
                                 date=d.meta.get("date"), deleted=iid in deleted))
    return out


@router.post("/portfolio/upload", response_model=list[PortfolioItem])
async def upload(file: UploadFile = File(...), user: dict = Depends(current_user)):
    """Add work (Markdown / text / PDF case study, or a CV). Re-indexed incrementally for this user only."""
    name = re.sub(r"[^A-Za-z0-9._-]", "_", file.filename or "upload.md")[:80]
    if not name.endswith((".md", ".txt", ".pdf")):
        raise HTTPException(415, "upload .md, .txt or .pdf")
    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(413, "file too large")
    dest = _udir(user) / "uploads" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    retriever.invalidate(user.get("persona") or "ai_ml", user["id"])
    s = dict(user.get("settings") or {})
    s["own_portfolio"] = True
    with engine().begin() as c:
        c.execute(update(users).where(users.c.id == user["id"]).values(settings=s))
    return portfolio({**user, "settings": s})


@router.delete("/portfolio/{item_id:path}")
def delete_item(item_id: str, user: dict = Depends(current_user)) -> dict:
    """Hide an evidence item from retrieval (it can no longer back a claim). Reversible from Settings."""
    s = dict(user.get("settings") or {})
    s["deleted_items"] = sorted(set(s.get("deleted_items", [])) | {item_id})
    with engine().begin() as c:
        c.execute(update(users).where(users.c.id == user["id"]).values(settings=s))
    return {"ok": True, "deleted_items": s["deleted_items"]}


@router.post("/portfolio/{item_id:path}/restore")
def restore_item(item_id: str, user: dict = Depends(current_user)) -> dict:
    s = dict(user.get("settings") or {})
    s["deleted_items"] = [i for i in s.get("deleted_items", []) if i != item_id]
    with engine().begin() as c:
        c.execute(update(users).where(users.c.id == user["id"]).values(settings=s))
    return {"ok": True}


# ---------------- memory viewer
@router.get("/memory", response_model=list[MemoryItem])
async def memory(user: dict = Depends(current_user)):
    items = await list_memory(dispatch.RT.store, user["id"])
    return [MemoryItem(namespace=i["namespace"], key=i["key"], rule=i.get("rule"),
                       value={k: v for k, v in i.items() if k not in ("namespace", "key")}) for i in items]


@router.delete("/memory")
async def delete_memory(namespace: str, key: str, user: dict = Depends(current_user)) -> dict:
    ns = tuple(namespace.split("/"))
    if len(ns) < 2 or ns[1] != user["id"] or ns[0] not in ("style", "outcome"):
        raise HTTPException(403, "not your memory")
    await dispatch.RT.store.adelete(ns, key)
    await dispatch.RT.store.adelete(("candidates", user["id"]), key)  # so it is not re-promoted from old counts
    return {"ok": True}


# ---------------- connected accounts
@router.get("/connect/upwork/start")
async def upwork_start(user: dict = Depends(current_user)) -> dict:
    try:
        return {"authorize_url": await upwork_oauth.start(user["id"])}
    except Exception as e:
        raise HTTPException(502, f"Upwork OAuth discovery failed: {type(e).__name__}")


@router.get("/connect/upwork/callback")
async def upwork_callback(code: str, state: str):
    await upwork_oauth.callback(code, state)
    return RedirectResponse("/settings?connected=upwork")


@router.get("/connect/status")
def connect_status(user: dict = Depends(current_user)) -> dict:
    return {"gigsim": True, "upwork": bool(load_oauth_tokens(user["id"], "upwork")),
            "mode": (user.get("settings") or {}).get("marketplace", "gigsim")}


# ---------------- health + demo
@router.get("/health", response_model=HealthOut)
async def health():
    h = get_health()
    mk = h.get("marketplace", {"ok": True, "detail": "no calls yet"})
    services = {}
    for name, url in {"marketplace": os.environ.get("MARKETPLACE_MCP_URL"), "workspace": os.environ.get("WORKSPACE_MCP_URL"),
                      "portfolio": os.environ.get("PORTFOLIO_MCP_URL")}.items():
        if not url or os.environ.get("GIGBID_MCP_INPROCESS") == "1":
            services[name] = "in-process"
            continue
        try:
            async with httpx.AsyncClient(timeout=2) as c:
                r = await c.get(url.rsplit("/mcp", 1)[0] + "/health")
            services[name] = "up" if r.status_code < 500 else "down"
        except Exception:
            services[name] = "down"
    if services.get("marketplace") == "down":
        mk = {"ok": False, "detail": "marketplace MCP server unreachable"}
    return HealthOut(ok=mk.get("ok", True), marketplace=mk, services=services, mode=config.get("marketplace.mode"),
                     profile=llm.current_profile())


@router.post("/demo/tick")
async def demo_tick(user: dict = Depends(current_user)) -> dict:
    """GigSim only: advance simulated time so clients view / reply (used in the demo and Playwright tests)."""
    url = os.environ.get("GIGSIM_URL", "http://localhost:8001")
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = (await c.post(f"{url}/v1/admin/tick")).json()
    except Exception:
        from gigsim_standin.app import sim

        r = sim.tick()
    await dispatch.enqueue("sync_pipeline", user_id=user["id"])
    return r
