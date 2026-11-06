"""Long-term memory: a LangGraph store (Postgres in deployment, SQLite locally, in-memory in tests).

Namespaces (only promoted knowledge lives here, see promotion_rules.py):
  ("style", user_id)              -> learned style rules, e.g. {"rule": "never say 'passionate'", "evidence": [...]}
  ("outcome", user_id, category)  -> what got replies / won in a category
  ("candidates", user_id)         -> NOT memory: pending candidates counted toward promotion (never read by agents)
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from langgraph.store.base import BaseStore

from core.db import database_url


@asynccontextmanager
async def open_store():
    url = os.environ.get("GIGBID_STORE_URL") or database_url()
    if url.startswith("postgresql"):
        from langgraph.store.postgres.aio import AsyncPostgresStore

        async with AsyncPostgresStore.from_conn_string(url.replace("postgresql+psycopg://", "postgresql://")) as store:
            await store.setup()
            yield store
    elif url.startswith("sqlite"):
        from langgraph.store.sqlite.aio import AsyncSqliteStore

        path = url.split("///", 1)[1].replace(".db", "_store.db")
        async with AsyncSqliteStore.from_conn_string(path) as store:
            await store.setup()
            yield store
    else:
        from langgraph.store.memory import InMemoryStore

        yield InMemoryStore()


async def style_rules(store: BaseStore | None, user_id: str) -> list[dict[str, Any]]:
    if store is None:
        return []
    return [i.value | {"key": i.key} for i in await store.asearch(("style", user_id), limit=50)]


async def outcome_insights(store: BaseStore | None, user_id: str, category: str | None) -> list[dict[str, Any]]:
    if store is None or not category:
        return []
    return [i.value | {"key": i.key} for i in await store.asearch(("outcome", user_id, category), limit=20)]


async def list_memory(store: BaseStore, user_id: str) -> list[dict[str, Any]]:
    out = []
    for ns in [("style", user_id)]:
        out += [{"namespace": list(ns), "key": i.key, **i.value} for i in await store.asearch(ns, limit=100)]
    for item in await store.asearch(("outcome", user_id), limit=200):
        out.append({"namespace": list(item.namespace), "key": item.key, **item.value})
    return out
