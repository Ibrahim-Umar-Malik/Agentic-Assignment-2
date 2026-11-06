"""Test-wide environment: isolated SQLite DB, offline model profile, anonymous in-memory MCP access."""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="gigbid-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ.setdefault("GIGBID_PROFILE", "offline")
os.environ.setdefault("MARKETPLACE_ALLOW_ANON", "1")
os.environ.setdefault("GIGSIM_STATE", f"{_tmp}/gigsim.json")
os.environ.setdefault("GIGSIM_ERROR_RATE", "0")
os.environ.setdefault("GIGBID_CHECKPOINT_URL", f"sqlite:///{_tmp}/checkpoints.db")

from core.db import init_db  # noqa: E402

init_db()
