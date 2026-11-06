"""Compile graphs with the durable checkpointer (Postgres in deployment; SQLite locally) and the memory store."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from core.db import database_url, sibling_sqlite_path

from .graphs.bid_graph import build_bid_graph
from .graphs.conversation_graph import build_conversation_graph
from .memory.store import open_store


@asynccontextmanager
async def open_checkpointer():
    url = os.environ.get("GIGBID_CHECKPOINT_URL") or database_url()
    if url.startswith("postgresql"):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(url.replace("postgresql+psycopg://", "postgresql://")) as cp:
            await cp.setup()
            yield cp
    elif url.startswith("sqlite"):
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        path = url.split("///", 1)[1] if os.environ.get("GIGBID_CHECKPOINT_URL") else sibling_sqlite_path(url, "checkpoints")
        async with AsyncSqliteSaver.from_conn_string(path) as cp:
            yield cp
    else:
        from langgraph.checkpoint.memory import InMemorySaver

        yield InMemorySaver()


class Runtime:
    """Holds compiled graphs for the lifetime of the API or worker process."""

    def __init__(self):
        self.bid = None
        self.conversation = None
        self._stack = None

    async def __aenter__(self):
        from contextlib import AsyncExitStack

        self._stack = AsyncExitStack()
        cp = await self._stack.enter_async_context(open_checkpointer())
        store = await self._stack.enter_async_context(open_store())
        self.checkpointer, self.store = cp, store
        self.bid = build_bid_graph().compile(checkpointer=cp, store=store)
        self.conversation = build_conversation_graph().compile(checkpointer=cp, store=store)
        return self

    async def __aexit__(self, *exc):
        await self._stack.aclose()
