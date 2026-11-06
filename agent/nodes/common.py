"""Shared node plumbing: versioned prompts, untrusted-data handling, step/token budgets, tracing per node."""

from __future__ import annotations

import functools
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from core import config, llm, tracing

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
_RISK = Path(__file__).resolve().parents[1] / "risk_patterns.yaml"


def load_prompt(name: str, **vars: Any) -> tuple[str, str]:
    """Return (version, text) for agent/prompts/<name>.md. Every prompt lives there; none are inline."""
    raw = (PROMPTS / f"{name}.md").read_text()
    version = "0"
    if raw.startswith("---"):
        head, _, raw = raw[3:].partition("---")
        version = str((yaml.safe_load(head) or {}).get("version", "0"))
    if "{untrusted_rules}" in raw:
        vars.setdefault("untrusted_rules", load_prompt("_untrusted")[1].strip())
    for k, v in vars.items():
        raw = raw.replace("{" + k + "}", str(v))
    return version, raw.strip()


@functools.lru_cache(maxsize=1)
def risk_patterns() -> dict[str, Any]:
    return yaml.safe_load(_RISK.read_text())


def injection_spans(text: str) -> list[str]:
    hits = []
    for pat in risk_patterns()["injection"]:
        for m in re.finditer(pat, text):
            hits.append(m.group(0))
    return hits


def sanitize_untrusted(text: str) -> tuple[str, list[str]]:
    """Defence layer 1: drop sentences that look like instructions to an AI before any model sees the post.
    GIGBID_DEFENCES=off disables layers 1 and 2; used only by the injection eval to measure attack success before
    defences (evals/runners/decision_eval.py --defences off). Never set it in production."""
    if os.environ.get("GIGBID_DEFENCES") == "off":
        return text, []
    sents = re.split(r"(?<=[.!?])\s+", text)
    kept, removed = [], []
    for s in sents:
        if injection_spans(s):
            removed.append(s)
        else:
            kept.append(s)
    return " ".join(kept), removed


def wrap(kind: str, text: str) -> str:
    """Defence layer 2: delimit untrusted text; neutralise attempts to close the tag early."""
    if os.environ.get("GIGBID_DEFENCES") == "off":
        return text
    safe = text.replace(f"</{kind}>", "").replace(f"<{kind}>", "")
    return f"<{kind}>\n{safe}\n</{kind}>"


def over_budget(state: dict) -> str | None:
    b = config.get("budgets", {})
    if state.get("steps", 0) > b.get("steps_per_thread", 40):
        return f"step budget exceeded ({state.get('steps')} > {b.get('steps_per_thread')})"
    if state.get("tokens", 0) > b.get("tokens_per_thread", 60000):
        return f"token budget exceeded ({state.get('tokens')} > {b.get('tokens_per_thread')})"
    return None


def node(name: str) -> Callable:
    """Wrap a node: trace span, token/cost metering, step counting, structured log entry."""

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(state: dict, *args: Any, **kwargs: Any) -> dict:
            if state.get("trace_id"):
                tracing.trace_id_var.set(state["trace_id"])
            if state.get("user_id"):
                tracing.user_id_var.set(state["user_id"])
            meter = llm.Meter()
            tok = llm.meter_var.set(meter)
            t0 = time.time()
            try:
                with tracing.span(f"node.{name}", "node", model=llm.model_for(name) if name in _MODEL_NODES else None) as sp:
                    out = await fn(state, *args, **kwargs) or {}
                    sp.update({"tokens": meter.tokens, "cost_usd": round(meter.cost_usd, 6),
                               "output_keys": sorted(out.keys())})
            finally:
                llm.meter_var.reset(tok)
            out = dict(out)
            out["steps"] = 1
            out["tokens"] = meter.tokens
            out["cost_usd"] = meter.cost_usd
            out["node_log"] = [{"node": name, "t": round(t0, 3), "latency_s": round(time.time() - t0, 3), "tokens": meter.tokens,
                                "cost_usd": round(meter.cost_usd, 6), "model": llm.model_for(name) if name in _MODEL_NODES else "rules",
                                "summary": out.pop("_summary", "")}]
            return out

        return wrapper

    return deco


_MODEL_NODES = {"analyst", "risk", "matcher", "pricing", "writer", "verifier", "critic", "compliance", "liaison", "intent"}
