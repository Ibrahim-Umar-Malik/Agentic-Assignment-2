"""Send long work to the worker (Arq on Redis), or run it in-process when no Redis is configured
(single-container deployments). Web requests never run a graph inline."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from agent import runner
from worker import tasks

log = logging.getLogger("gigbid.dispatch")
_pool = None
_inflight: dict[str, asyncio.Task] = {}
RT: Any = None  # set by main.lifespan


async def _arq():
    global _pool
    if _pool is None:
        from arq import create_pool
        from arq.connections import RedisSettings

        _pool = await create_pool(RedisSettings.from_dsn(os.environ["REDIS_URL"]))
    return _pool


def use_worker() -> bool:
    return bool(os.environ.get("REDIS_URL")) and os.environ.get("GIGBID_INLINE_WORKER") != "1"


async def enqueue(name: str, **kw: Any) -> None:
    key = {"analyze_job": f"analyze:{kw.get('user_id')}:{kw.get('job_id')}", "sync_pipeline": f"sync:{kw.get('user_id')}",
           "resume": f"resume:{kw.get('thread_id')}"}.get(name, name)
    if use_worker():
        await (await _arq()).enqueue_job(name, _job_id=key if name != "resume" else None, **kw)
        return
    if key in _inflight and not _inflight[key].done():
        return  # same de-duplication the Arq job id gives
    _inflight[key] = asyncio.create_task(_run(name, **kw))


async def _run(name: str, **kw: Any) -> Any:
    try:
        if name == "analyze_job":
            return await runner.analyze_job(RT, kw["user_id"], kw["job_id"])
        if name == "resume":
            return await runner.resume(RT, kw["user_id"], kw["thread_id"], kw.get("decision"))
        if name == "sync_pipeline":
            return await tasks.sync_pipeline(RT, enqueue, kw["user_id"])
    except Exception:
        log.exception("inline task %s failed", name)


async def inline_scheduler(stop: asyncio.Event, every_s: int = 60) -> None:
    while not stop.is_set():
        try:
            await tasks.scheduler_tick(RT, enqueue)
        except Exception:
            log.exception("scheduler tick failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=every_s)
        except TimeoutError:
            pass
