"""Arq worker: scheduled scouting (cron), analyses, resumes after approval and pipeline sync, off the web
request path. Run: arq worker.main.WorkerSettings"""

from __future__ import annotations

import os

from arq import cron
from arq.connections import RedisSettings

from agent import runner
from agent.runtime import Runtime
from core.db import init_db
from core.pii import install_logging

from . import tasks


async def _enqueue(ctx_redis, name: str, **kw):
    job_id = {"analyze_job": f"analyze:{kw.get('user_id')}:{kw.get('job_id')}",
              "sync_pipeline": f"sync:{kw.get('user_id')}"}.get(name)
    await ctx_redis.enqueue_job(name, _job_id=job_id, **kw)  # Arq de-duplicates by job id


async def startup(ctx):
    install_logging()
    init_db()
    ctx["rt"] = await Runtime().__aenter__()
    await runner.recover_decided(ctx["rt"])  # crash recovery: finish approvals that were decided but not completed


async def shutdown(ctx):
    await ctx["rt"].__aexit__(None, None, None)


async def analyze_job(ctx, user_id: str, job_id: str):
    return await runner.analyze_job(ctx["rt"], user_id, job_id)


async def resume(ctx, user_id: str, thread_id: str, decision: dict | None):
    return await runner.resume(ctx["rt"], user_id, thread_id, decision)


async def sync_pipeline(ctx, user_id: str):
    return await tasks.sync_pipeline(ctx["rt"], lambda n, **k: _enqueue(ctx["redis"], n, **k), user_id)


async def scheduler(ctx):
    return await tasks.scheduler_tick(ctx["rt"], lambda n, **k: _enqueue(ctx["redis"], n, **k))


class WorkerSettings:
    functions = [analyze_job, resume, sync_pipeline]
    cron_jobs = [cron(scheduler, minute=set(range(0, 60, 2)), run_at_startup=True)]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    max_jobs = 4
    job_timeout = 600
