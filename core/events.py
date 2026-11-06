"""Run-progress event bus: Redis pub/sub when REDIS_URL is set (API and worker are separate processes),
otherwise in-process asyncio queues. Events are also appended to a short per-run history so a client that
connects late (or refreshes) replays what it missed."""

from __future__ import annotations

import asyncio
import json
import os
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from typing import Any

_local_subs: dict[str, list[asyncio.Queue]] = defaultdict(list)
_local_hist: dict[str, deque] = defaultdict(lambda: deque(maxlen=500))


def _redis():
    url = os.environ.get("REDIS_URL")
    if not url:
        return None
    import redis.asyncio as aioredis

    return aioredis.from_url(url, decode_responses=True)


async def publish(channel: str, event: dict[str, Any]) -> None:
    data = json.dumps(event, default=str)
    r = _redis()
    if r is not None:
        try:
            await r.rpush(f"hist:{channel}", data)
            await r.ltrim(f"hist:{channel}", -500, -1)
            await r.expire(f"hist:{channel}", 86400)
            await r.publish(channel, data)
            await r.aclose()
            return
        except Exception:
            pass
    _local_hist[channel].append(data)
    for q in list(_local_subs[channel]):
        q.put_nowait(data)


async def subscribe(channel: str) -> AsyncIterator[dict[str, Any]]:
    r = _redis()
    if r is not None:
        try:
            for data in await r.lrange(f"hist:{channel}", 0, -1):
                yield json.loads(data)
            ps = r.pubsub()
            await ps.subscribe(channel)
            try:
                while True:
                    msg = await ps.get_message(ignore_subscribe_messages=True, timeout=15)
                    if msg is None:
                        yield {"type": "ping"}
                        continue
                    yield json.loads(msg["data"])
            finally:
                await ps.unsubscribe(channel)
                await r.aclose()
            return
        except Exception:
            pass
    q: asyncio.Queue = asyncio.Queue()
    for data in list(_local_hist[channel]):
        q.put_nowait(data)
    _local_subs[channel].append(q)
    try:
        while True:
            try:
                data = await asyncio.wait_for(q.get(), timeout=15)
                yield json.loads(data)
            except TimeoutError:
                yield {"type": "ping"}
    finally:
        _local_subs[channel].remove(q)
