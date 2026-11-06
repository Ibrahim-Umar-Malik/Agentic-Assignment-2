"""Encryption for OAuth tokens at rest (E4). Key from TOKEN_ENCRYPTION_KEY (a Fernet key); never logged."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from typing import Any

from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    key = os.environ.get("TOKEN_ENCRYPTION_KEY")
    if not key:
        if os.environ.get("GIGBID_ENV", "dev") == "production":
            raise RuntimeError("TOKEN_ENCRYPTION_KEY must be set in production")
        # dev-only derived key so local runs work; production refuses to start without a real key
        key = base64.urlsafe_b64encode(hashlib.sha256(b"gigbid-dev-only-key").digest()).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_json(obj: Any) -> str:
    return _fernet().encrypt(json.dumps(obj).encode()).decode()


def decrypt_json(token: str) -> Any:
    return json.loads(_fernet().decrypt(token.encode()))


def save_oauth_tokens(user_id: str, provider: str, tokens: dict[str, Any]) -> None:
    from sqlalchemy import delete

    from .db import engine, oauth_tokens

    tokens = {**tokens, "obtained_at": tokens.get("obtained_at", time.time())}
    with engine().begin() as c:
        c.execute(delete(oauth_tokens).where(oauth_tokens.c.user_id == user_id, oauth_tokens.c.provider == provider))
        c.execute(oauth_tokens.insert().values(user_id=user_id, provider=provider, ciphertext=encrypt_json(tokens), updated_at=time.time()))


def load_oauth_tokens(user_id: str, provider: str) -> dict[str, Any] | None:
    from sqlalchemy import select

    from .db import engine, oauth_tokens

    with engine().begin() as c:
        row = c.execute(select(oauth_tokens.c.ciphertext).where(oauth_tokens.c.user_id == user_id,
                                                               oauth_tokens.c.provider == provider)).first()
    return decrypt_json(row[0]) if row else None
