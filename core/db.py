"""Application database (Postgres in deployment, SQLite for local dev and tests). Every query is tenant-scoped."""

from __future__ import annotations

import json
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    event,
    text,
)
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parents[1]
metadata = MetaData()


def now() -> float:
    return time.time()


users = Table("users", metadata,
              Column("id", String, primary_key=True), Column("email", String, unique=True, nullable=False),
              Column("password_hash", String, nullable=False), Column("name", String), Column("persona", String),
              Column("settings", JSON, default=dict), Column("created_at", Float, default=now))
sessions = Table("sessions", metadata, Column("token_hash", String, primary_key=True), Column("user_id", String, index=True),
                 Column("expires_at", Float))
oauth_tokens = Table("oauth_tokens", metadata, Column("user_id", String, primary_key=True), Column("provider", String, primary_key=True),
                     Column("ciphertext", Text, nullable=False), Column("updated_at", Float, default=now))
jobs = Table("jobs", metadata,
             Column("user_id", String, primary_key=True), Column("job_id", String, primary_key=True),
             Column("data", JSON), Column("status", String, default="queued"), Column("action", String),
             Column("fit", Float), Column("risk", Float), Column("price", Float), Column("connects", Integer),
             Column("thread_id", String), Column("summary", JSON), Column("dedup_key", String, index=True),
             Column("created_at", Float, default=now), Column("updated_at", Float, default=now))
runs = Table("runs", metadata,
             Column("id", String, primary_key=True), Column("user_id", String, index=True), Column("job_id", String),
             Column("graph", String), Column("thread_id", String, index=True), Column("status", String),
             Column("trace_id", String), Column("started_at", Float, default=now), Column("finished_at", Float),
             Column("tokens", Integer, default=0), Column("cost_usd", Float, default=0.0), Column("error", Text))
approvals = Table("approvals", metadata,
                  Column("id", String, primary_key=True), Column("user_id", String, index=True), Column("thread_id", String, index=True),
                  Column("graph", String), Column("kind", String), Column("job_id", String), Column("payload", JSON),
                  Column("status", String, default="pending"), Column("decision", JSON),
                  Column("created_at", Float, default=now), Column("decided_at", Float))
trace_spans = Table("trace_spans", metadata,
                    Column("id", Integer, primary_key=True, autoincrement=True), Column("trace_id", String, index=True),
                    Column("user_id", String), Column("name", String), Column("kind", String), Column("start", Float),
                    Column("end", Float), Column("attrs", JSON))
audit_log = Table("audit_log", metadata,
                  Column("id", Integer, primary_key=True, autoincrement=True), Column("ts", Float, default=now),
                  Column("user_id", String, index=True), Column("tool", String), Column("args", JSON), Column("result", JSON),
                  Column("trace_id", String, index=True))
idempotency = Table("idempotency", metadata, Column("key", String, primary_key=True), Column("user_id", String),
                    Column("result", JSON), Column("created_at", Float, default=now))
saved_searches = Table("saved_searches", metadata,
                       Column("id", String, primary_key=True), Column("user_id", String, index=True), Column("query", String),
                       Column("category", String), Column("interval_min", Integer), Column("last_run", Float, default=0.0))
pipeline = Table("pipeline", metadata, Column("user_id", String, primary_key=True), Column("job_id", String, primary_key=True),
                 Column("stage", String), Column("title", String), Column("proposal_id", String), Column("thread_id", String),
                 Column("bid", Float), Column("connects", Integer), Column("category", String), Column("updated_at", Float, default=now))
dead_letter = Table("dead_letter", metadata, Column("id", Integer, primary_key=True, autoincrement=True),
                    Column("user_id", String), Column("job_id", String), Column("thread_id", String), Column("error", Text),
                    Column("ts", Float, default=now))
edits = Table("edits", metadata, Column("id", Integer, primary_key=True, autoincrement=True), Column("user_id", String, index=True),
              Column("thread_id", String), Column("before", Text), Column("after", Text), Column("diff", JSON),
              Column("ts", Float, default=now))
conversations = Table("conversations", metadata, Column("user_id", String, primary_key=True), Column("thread_id", String, primary_key=True),
                      Column("job_id", String), Column("data", JSON), Column("status", String), Column("last_seen_msg", String),
                      Column("graph_thread", String), Column("updated_at", Float, default=now))
kv = Table("kv", metadata, Column("key", String, primary_key=True), Column("value", JSON))


def database_url() -> str:
    url = os.environ.get("DATABASE_URL") or f"sqlite:///{ROOT / 'var' / 'gigbid.db'}"
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


@lru_cache(maxsize=4)
def engine(url: str | None = None) -> Engine:
    url = url or database_url()
    if url.startswith("sqlite"):
        Path(url.split("///", 1)[1]).parent.mkdir(parents=True, exist_ok=True)
        eng = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(eng, "connect")
        def _wal(dbapi_conn, _):  # concurrent API + worker + MCP servers on one file
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
            dbapi_conn.execute("PRAGMA busy_timeout=30000")
    else:
        eng = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)
    return eng


def init_db(url: str | None = None) -> Engine:
    eng = engine(url)
    metadata.create_all(eng)
    if eng.dialect.name == "postgresql":
        with eng.begin() as c:  # append-only audit log, enforced by the database itself
            c.execute(text("""
                CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger AS $$
                BEGIN RAISE EXCEPTION 'audit_log is append-only'; END; $$ LANGUAGE plpgsql;"""))
            c.execute(text("DROP TRIGGER IF EXISTS audit_log_no_change ON audit_log"))
            c.execute(text("CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log "
                           "FOR EACH ROW EXECUTE FUNCTION audit_log_append_only()"))
    else:
        with eng.begin() as c:
            c.execute(text("CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log "
                           "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END"))
            c.execute(text("CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log "
                           "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END"))
    return eng


def row_dict(row: Any) -> dict:
    d = dict(row._mapping)
    for k, v in d.items():
        if isinstance(v, str) and k in ("data", "payload", "attrs", "settings") and v[:1] in "[{":
            try:
                d[k] = json.loads(v)
            except json.JSONDecodeError:
                pass
    return d
