"""OAuth 2.1 (authorization code + PKCE) against Upwork's MCP server, per user; tokens stored encrypted.

Discovery follows the MCP authorization spec: the protected-resource metadata of the MCP server names the
authorization server; its metadata gives the endpoints. Dynamic client registration is used when the server
supports it, otherwise UPWORK_CLIENT_ID / UPWORK_CLIENT_SECRET from the environment.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import select

from core.crypto import encrypt_json, save_oauth_tokens
from core.db import engine, kv

MCP_URL = os.environ.get("UPWORK_MCP_URL", "https://mcp.upwork.com/mcp")


def redirect_uri() -> str:
    return os.environ.get("PUBLIC_BASE_URL", "http://localhost:8080").rstrip("/") + "/api/connect/upwork/callback"


async def discover() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as c:
        base = MCP_URL.split("/mcp")[0]
        prm = (await c.get(f"{base}/.well-known/oauth-protected-resource")).json()
        issuer = prm["authorization_servers"][0].rstrip("/")
        meta = (await c.get(f"{issuer}/.well-known/oauth-authorization-server")).json()
    return meta


async def client_credentials(meta: dict) -> dict[str, str]:
    if os.environ.get("UPWORK_CLIENT_ID"):
        return {"client_id": os.environ["UPWORK_CLIENT_ID"], "client_secret": os.environ.get("UPWORK_CLIENT_SECRET", "")}
    with engine().begin() as c:
        row = c.execute(select(kv.c.value).where(kv.c.key == "upwork:client")).first()
    if row:
        return row[0]
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(meta["registration_endpoint"], json={
            "client_name": "GigBid", "redirect_uris": [redirect_uri()], "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"], "token_endpoint_auth_method": "none"})
        r.raise_for_status()
        creds = {"client_id": r.json()["client_id"], "client_secret": r.json().get("client_secret", "")}
    with engine().begin() as c:
        c.execute(kv.insert().values(key="upwork:client", value=creds))
    return creds


async def start(user_id: str) -> str:
    meta = await discover()
    creds = await client_credentials(meta)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    with engine().begin() as c:  # PKCE verifier stored encrypted server-side, keyed by state
        c.execute(kv.insert().values(key=f"oauth:{state}", value={"user_id": user_id, "v": encrypt_json(verifier), "ts": time.time()}))
    return meta["authorization_endpoint"] + "?" + urlencode({
        "response_type": "code", "client_id": creds["client_id"], "redirect_uri": redirect_uri(), "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256", "resource": MCP_URL})


async def callback(code: str, state: str) -> str:
    from core.crypto import decrypt_json

    with engine().begin() as c:
        row = c.execute(select(kv.c.value).where(kv.c.key == f"oauth:{state}")).first()
        c.execute(kv.delete().where(kv.c.key == f"oauth:{state}"))
    if not row or time.time() - row[0]["ts"] > 600:
        raise ValueError("invalid or expired OAuth state")
    meta = await discover()
    creds = await client_credentials(meta)
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(meta["token_endpoint"], data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(), "client_id": creds["client_id"],
            "code_verifier": decrypt_json(row[0]["v"]), "resource": MCP_URL,
            **({"client_secret": creds["client_secret"]} if creds.get("client_secret") else {})})
        r.raise_for_status()
        tok = r.json()
    tok["expires_at"] = time.time() + int(tok.get("expires_in", 3600))
    save_oauth_tokens(row[0]["user_id"], "upwork", tok)
    return row[0]["user_id"]


async def refresh(user_id: str, tokens: dict) -> dict:
    meta = await discover()
    creds = await client_credentials(meta)
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(meta["token_endpoint"], data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
                                                       "client_id": creds["client_id"], "resource": MCP_URL})
        r.raise_for_status()
        new = {**tokens, **r.json()}
    new["expires_at"] = time.time() + int(new.get("expires_in", 3600))
    save_oauth_tokens(user_id, "upwork", new)
    return new
