"""One trace id from the UI request through the API, the graph, every MCP server and the audit log (E3).

Spans are written (PII-masked) to the trace_spans table, which the web UI renders at /runs/:id and shares
read-only at /share/trace/:id. If LANGFUSE_PUBLIC_KEY/SECRET_KEY are set, spans are mirrored to Langfuse.
"""

from __future__ import annotations

import contextvars
import logging
import os
import time
import uuid
from contextlib import contextmanager
from typing import Any

from .pii import mask

log = logging.getLogger("gigbid.trace")
trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)
user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id", default=None)
TRACE_HEADER = "x-gigbid-trace-id"

_langfuse = None
if os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"):
    try:  # optional dependency
        from langfuse import Langfuse  # type: ignore

        _langfuse = Langfuse()
    except Exception:  # pragma: no cover
        _langfuse = None


def new_trace_id() -> str:
    return uuid.uuid4().hex


def current_trace_id() -> str:
    tid = trace_id_var.get()
    if not tid:
        tid = new_trace_id()
        trace_id_var.set(tid)
    return tid


def _write(trace_id: str, name: str, kind: str, start: float, end: float, attrs: dict[str, Any]) -> None:
    try:
        from .db import engine, trace_spans

        with engine().begin() as c:
            c.execute(trace_spans.insert().values(trace_id=trace_id, user_id=user_id_var.get(), name=name, kind=kind,
                                                  start=start, end=end, attrs=mask(attrs)))
    except Exception as e:  # tracing must never break the product
        log.debug("trace write failed: %s", e)
    if _langfuse is not None:
        try:
            _langfuse.trace(id=trace_id, name="gigbid").span(name=name, metadata=mask(attrs), start_time=None)
        except Exception:
            pass


def record(name: str, kind: str = "event", **attrs: Any) -> None:
    t = time.time()
    _write(current_trace_id(), name, kind, t, t, attrs)


@contextmanager
def span(name: str, kind: str = "node", **attrs: Any):
    tid = current_trace_id()
    start = time.time()
    extra: dict[str, Any] = {}
    try:
        yield extra
    except Exception as e:
        extra["error"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        _write(tid, name, kind, start, time.time(), {**attrs, **extra})


def trace_url(trace_id: str) -> str:
    base = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8080").rstrip("/")
    return f"{base}/share/trace/{trace_id}"
