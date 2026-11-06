"""Short-lived HMAC bearer tokens the API/worker present to GigBid's own MCP servers (per user, per call)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time


def _secret() -> bytes:
    s = os.environ.get("MCP_SHARED_SECRET")
    if not s:
        if os.environ.get("GIGBID_ENV", "dev") == "production":
            raise RuntimeError("MCP_SHARED_SECRET must be set in production")
        s = "gigbid-dev-only-secret"
    return s.encode()


def issue(user_id: str, ttl_s: int = 900) -> str:
    body = f"{user_id}|{int(time.time()) + ttl_s}"
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{body}|{sig}".encode()).decode()


def verify(token: str) -> str | None:
    try:
        user_id, exp, sig = base64.urlsafe_b64decode(token.encode()).decode().rsplit("|", 2)
    except Exception:
        return None
    good = hmac.new(_secret(), f"{user_id}|{exp}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(good, sig) or int(exp) < time.time():
        return None
    return user_id


# In-process MCP sessions (tests, evals, single-process dev) carry the caller's user id in a context variable,
# because there is no HTTP request to authenticate. Only reachable from inside the same Python process.
import contextvars  # noqa: E402

inprocess_user: contextvars.ContextVar[str | None] = contextvars.ContextVar("inprocess_user", default=None)
