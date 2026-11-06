"""Load agent/config.yaml with ${VAR:-default} expansion and optional JSON overrides."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(os.environ.get("GIGBID_CONFIG", ROOT / "agent" / "config.yaml"))
_VAR = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def _expand(text: str) -> str:
    return _VAR.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), text)


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    cfg = yaml.safe_load(_expand(CONFIG_PATH.read_text()))
    if os.environ.get("GIGBID_CONFIG_OVERRIDES"):
        cfg = _merge(cfg, json.loads(os.environ["GIGBID_CONFIG_OVERRIDES"]))
    return cfg


def reload_config() -> dict[str, Any]:
    load_config.cache_clear()
    return load_config()


def get(path: str, default: Any = None) -> Any:
    node: Any = load_config()
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


@lru_cache(maxsize=1)
def policy_rules() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "data" / "policy_pack" / "rules.yaml").read_text())
