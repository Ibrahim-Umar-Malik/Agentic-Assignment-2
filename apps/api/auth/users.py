"""Users and sessions. Passwords: scrypt. Session tokens: random, stored only as SHA-256 hashes."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from core import tracing
from core.db import engine, row_dict, sessions, users

SESSION_TTL = 14 * 86400


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${dk.hex()}"


def check_password(pw: str, stored: str) -> bool:
    try:
        _, salt, dk = stored.split("$")
        return hmac.compare_digest(hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1).hex(), dk)
    except Exception:
        return False


def create_user(email: str, password: str, name: str = "", persona: str = "ai_ml", settings: dict | None = None) -> dict:
    uid = "u-" + uuid.uuid4().hex[:12]
    defaults = {"hourly_floor": 40, "weekly_connects_budget": 60, "autonomy": "suggest", "marketplace": "gigsim",
                "hours_per_week": 20, "deleted_items": [], "onboarded": False}
    with engine().begin() as c:
        c.execute(users.insert().values(id=uid, email=email.lower(), password_hash=hash_password(password), name=name,
                                        persona=persona, settings={**defaults, **(settings or {})}, created_at=time.time()))
    return get_user(uid)


def get_user(uid: str) -> dict | None:
    with engine().begin() as c:
        row = c.execute(select(users).where(users.c.id == uid)).first()
    return row_dict(row) if row else None


def find_user(email: str) -> dict | None:
    with engine().begin() as c:
        row = c.execute(select(users).where(users.c.email == email.lower())).first()
    return row_dict(row) if row else None


def new_session(uid: str) -> str:
    tok = secrets.token_urlsafe(32)
    with engine().begin() as c:
        c.execute(sessions.insert().values(token_hash=hashlib.sha256(tok.encode()).hexdigest(), user_id=uid,
                                           expires_at=time.time() + SESSION_TTL))
    return tok


def end_session(tok: str) -> None:
    with engine().begin() as c:
        c.execute(sessions.delete().where(sessions.c.token_hash == hashlib.sha256(tok.encode()).hexdigest()))


def _token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get("gigbid_session")


def current_user(request: Request) -> dict:
    tok = _token(request)
    if not tok:
        raise HTTPException(401, "not signed in")
    with engine().begin() as c:
        row = c.execute(select(sessions).where(sessions.c.token_hash == hashlib.sha256(tok.encode()).hexdigest())).first()
    if not row or row.expires_at < time.time():
        raise HTTPException(401, "session expired")
    user = get_user(row.user_id)
    if not user:
        raise HTTPException(401, "unknown user")
    tracing.user_id_var.set(user["id"])
    return user


CurrentUser = Depends(current_user)
