"""Model routing by node (set in agent/config.yaml, never in code), with fallback, timeouts, retries and metering.

A node calls `structured(node, prompt, payload, Schema)`. If the node's model is `offline/heuristic` (CI or no
API key), the router returns None and the node uses its deterministic heuristic path. Token counts, cost and
latency of every call are added to the current trace span and to the per-thread meter used for budgets.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel

from . import config, tracing

log = logging.getLogger("gigbid.llm")
T = TypeVar("T", bound=BaseModel)


@dataclass
class Meter:
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    calls: int = 0
    by_node: dict[str, dict[str, float]] = field(default_factory=dict)

    def add(self, node: str, tin: int, tout: int, cost: float, latency: float) -> None:
        self.tokens_in += tin
        self.tokens_out += tout
        self.cost_usd += cost
        self.calls += 1
        n = self.by_node.setdefault(node, {"tokens": 0, "cost_usd": 0.0, "latency_s": 0.0, "calls": 0})
        n["tokens"] += tin + tout
        n["cost_usd"] += cost
        n["latency_s"] += latency
        n["calls"] += 1

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out


meter_var: contextvars.ContextVar[Meter | None] = contextvars.ContextVar("meter", default=None)


def current_profile() -> str:
    return os.environ.get("GIGBID_PROFILE") or config.get("profile", "open")


def model_for(node: str, profile: str | None = None) -> str:
    prof = config.get("profiles", {})[profile or current_profile()]
    return prof.get("nodes", {}).get(node) or prof["default"]


def fallback_for(profile: str | None = None) -> str:
    return config.get("profiles", {})[profile or current_profile()].get("fallback", "offline/heuristic")


def is_offline(node: str) -> bool:
    return model_for(node).startswith("offline/")


def _provider_ready(model: str) -> bool:
    prov = config.get("providers", {}).get(model.split("/", 1)[0], {})
    if prov.get("kind") == "offline":
        return False
    env = prov.get("api_key_env")
    return not env or bool(os.environ.get(env))


def _chat_model(model: str):
    provider, name = model.split("/", 1)
    prov = config.get("providers")[provider]
    temp = config.get("llm.temperature", 0.2)
    timeout = config.get("llm.timeout_s", 45)
    if prov["kind"] == "openai_compatible":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=name, base_url=prov["base_url"], api_key=os.environ[prov["api_key_env"]],
                          temperature=temp, timeout=timeout, max_retries=0)
    if prov["kind"] == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=name, base_url=prov["base_url"], temperature=temp)
    if prov["kind"] == "anthropic":
        from langchain_anthropic import ChatAnthropic  # type: ignore  # optional: paid profile only

        return ChatAnthropic(model=name, temperature=temp, timeout=timeout, max_retries=0)
    raise ValueError(f"unknown provider kind for {model}")


def price(model: str, tin: int, tout: int) -> float:
    p_in, p_out = config.get("prices", {}).get(model, [0, 0])
    return (tin * p_in + tout * p_out) / 1_000_000


async def _invoke(model: str, messages: list[tuple[str, str]], schema: type[T] | None, node: str) -> tuple[Any, int, int]:
    chat = _chat_model(model)
    if schema is not None:
        runnable = chat.with_structured_output(schema, include_raw=True)
        out = await asyncio.wait_for(runnable.ainvoke(messages), timeout=config.get("llm.timeout_s", 45))
        raw = out.get("raw")
        usage = getattr(raw, "usage_metadata", None) or {}
        if out.get("parsing_error") or out.get("parsed") is None:
            raise ValueError(f"structured output failed for {node}: {out.get('parsing_error')}")
        return out["parsed"], usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    msg = await asyncio.wait_for(chat.ainvoke(messages), timeout=config.get("llm.timeout_s", 45))
    usage = getattr(msg, "usage_metadata", None) or {}
    return msg.content, usage.get("input_tokens", 0), usage.get("output_tokens", 0)


async def call(node: str, system: str, user: str, schema: type[T] | None = None) -> Any | None:
    """Call the node's model; on failure retry with backoff, then the fallback model. None means 'use heuristic'."""
    candidates = [model_for(node), fallback_for()]
    retries = int(config.get("llm.max_retries", 2))
    messages = [("system", system), ("user", user)]
    for model in dict.fromkeys(candidates):
        if not _provider_ready(model):
            continue
        for attempt in range(retries + 1):
            t0 = time.time()
            try:
                result, tin, tout = await _invoke(model, messages, schema, node)
                lat = time.time() - t0
                cost = price(model, tin, tout)
                m = meter_var.get()
                if m is not None:
                    m.add(node, tin, tout, cost, lat)
                tracing.record(f"llm.{node}", "llm", model=model, tokens_in=tin, tokens_out=tout, cost_usd=round(cost, 6),
                               latency_s=round(lat, 3), attempt=attempt)
                return result
            except Exception as e:  # timeouts, 429s, 5xx, bad JSON
                tracing.record(f"llm.{node}.error", "llm", model=model, error=str(e)[:300], attempt=attempt)
                log.warning("llm %s (%s) attempt %d failed: %s", node, model, attempt, e)
                await asyncio.sleep(min(8, 0.5 * 2**attempt))
    return None


def to_json(obj: Any) -> str:
    if isinstance(obj, BaseModel):
        return obj.model_dump_json(indent=1)
    return json.dumps(obj, indent=1, default=str)
