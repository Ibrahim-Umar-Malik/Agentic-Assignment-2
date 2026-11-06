"""A small skill ontology: canonical skill names, aliases and plain-language phrasings clients use.

Used for requirement decomposition (V1), corrective re-querying (V8) and the claim verifier. Extend it in
config rather than code if your persona has other skills: GIGBID_SKILL_ALIASES (JSON) is merged in.
"""

from __future__ import annotations

import json
import os
import re

ALIASES: dict[str, list[str]] = {
    "Celery": ["background task queue", "task queue", "background jobs", "async workers", "job queue"],
    "RAG": ["retrieval-augmented", "answers from our own documents", "chat with documents", "document q&a", "chatbot over docs"],
    "LangGraph": ["agent workflow framework", "agentic workflow", "multi-agent", "agent orchestration"],
    "LangChain": ["llm framework"],
    "pgvector": ["vector search inside postgres", "postgres vector"],
    "Pinecone": ["managed vector database", "vector database", "vector db"],
    "dbt": ["transformation models", "data build tool", "analytics engineering"],
    "Power BI": ["microsoft dashboards", "powerbi", "pbi"],
    "A/B testing": ["split testing", "split test", "experiments", "ab test", "a/b test"],
    "WebSockets": ["real-time updates", "realtime", "live updates", "socket"],
    "React Native": ["cross-platform mobile app", "ios and android app", "mobile app"],
    "Stripe": ["online payments", "subscriptions billing", "payment integration"],
    "Playwright": ["automated browser tests", "end-to-end tests", "e2e tests"],
    "LoRA": ["parameter-efficient fine-tuning", "peft", "adapter fine-tuning"],
    "YOLO": ["object detection", "detect objects"],
    "fine-tuning": ["fine-tune", "finetune", "custom model training"],
    "OCR": ["text from scanned", "extract text from images", "document extraction"],
    "Next.js": ["nextjs", "next js"],
    "Node.js": ["nodejs", "node"],
    "Google Analytics 4": ["ga4", "google analytics"],
    "Snowflake": ["cloud data warehouse"],
    "Airflow": ["scheduled pipelines", "workflow orchestration", "dags"],
    "Excel": ["spreadsheet", "spreadsheets", "xlsx"],
    "Tableau": ["tableau dashboards"],
    "forecasting": ["forecast", "predict demand", "time series"],
    "LLM agents": ["ai agent", "ai agents", "autonomous agent"],
    "Kubernetes": ["k8s"],
    "statistics": ["statistical", "significance"],
}


def _load_extra() -> dict[str, list[str]]:
    raw = os.environ.get("GIGBID_SKILL_ALIASES")
    return json.loads(raw) if raw else {}


def all_aliases() -> dict[str, list[str]]:
    out = {k: list(v) for k, v in ALIASES.items()}
    for k, v in _load_extra().items():
        out.setdefault(k, []).extend(v)
    return out


def find_skills(text: str, vocabulary: list[str]) -> list[str]:
    """Canonical skills mentioned in text, by exact name (word-bounded) or by alias phrase."""
    low = text.lower()
    found: list[str] = []
    for s in sorted(set(vocabulary) | set(ALIASES), key=len, reverse=True):
        pat = r"(?<![a-z0-9])" + re.escape(s.lower()) + r"(?![a-z0-9])"
        if re.search(pat, low):
            found.append(s)
            continue
        for a in all_aliases().get(s, []):
            if a in low:
                found.append(s)
                break
    return list(dict.fromkeys(found))


def expand(requirement: str) -> str:
    """Query expansion for corrective retrieval: add canonical names for alias phrases and vice versa."""
    low = requirement.lower()
    extra = []
    for canon, aliases in all_aliases().items():
        if canon.lower() in low:
            extra.extend(aliases[:2])
        elif any(a in low for a in aliases):
            extra.append(canon)
    return requirement + (" " + " ".join(extra) if extra else "")
