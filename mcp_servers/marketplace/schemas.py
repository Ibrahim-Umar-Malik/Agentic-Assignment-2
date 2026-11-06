"""Pydantic input/output schemas for the Marketplace MCP server (A2)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

IdemKey = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9:_\-.]+$",
                description="Unique per intended action; a retried call with the same key never acts twice.")


class Job(BaseModel):
    id: str
    title: str
    description: str = ""
    skills: list[str] = []
    category: str | None = None
    budget_type: str | None = None
    budget: float | None = None
    client_id: str | None = None
    connects_cost: int | None = None
    screening_questions: list[str] = []
    posted_at: str | None = None


class JobList(BaseModel):
    jobs: list[Job]
    marketplace: str


class ClientHistory(BaseModel):
    id: str
    payment_verified: bool | None = None
    total_spent: float | None = None
    hires: int | None = None
    jobs_posted: int | None = None
    avg_rating: float | None = None
    member_since: str | None = None
    country: str | None = None
    industry: str | None = None
    recent_jobs: list[dict[str, Any]] = []
    note: str | None = None


class MarketStats(BaseModel):
    category: str
    n: int = 0
    budget_type: str | None = None
    p25: float | None = None
    median: float | None = None
    p75: float | None = None
    source: str | None = None


class ConnectsBalance(BaseModel):
    connects: int | None
    weekly_allowance: int | None = None
    note: str | None = None


class Message(BaseModel):
    id: str
    sender: str = Field(alias="from")
    body: str
    ts: float | None = None
    model_config = {"populate_by_name": True}


class Thread(BaseModel):
    id: str
    job_id: str | None = None
    client_id: str | None = None
    proposal_id: str | None = None
    messages: list[Message] = []


class ThreadList(BaseModel):
    threads: list[Thread]


class ProposalSummary(BaseModel):
    id: str
    job_id: str
    status: str
    bid_amount: float | None = None
    connects_spent: int | None = None


class ProposalList(BaseModel):
    proposals: list[ProposalSummary]


class EventList(BaseModel):
    events: list[dict[str, Any]]


class CreateDraftIn(BaseModel):
    job_id: str = Field(min_length=1, max_length=64)
    cover_letter: str = Field(min_length=50, max_length=5000)
    bid_amount: float = Field(gt=0, le=100000)
    answers: list[str] = Field(default_factory=list, max_length=10)
    idempotency_key: str = IdemKey
    dry_run: bool = Field(default=False, description="Return exactly what would be sent and what it costs, without sending.")


class SubmitIn(BaseModel):
    draft_id: str = Field(min_length=1, max_length=64)
    job_id: str = Field(min_length=1, max_length=64, description="Job the draft belongs to (for cost preview).")
    idempotency_key: str = IdemKey
    dry_run: bool = False


class SendMessageIn(BaseModel):
    thread_id: str = Field(min_length=1, max_length=64)
    body: str = Field(min_length=1, max_length=5000)
    idempotency_key: str = IdemKey
    dry_run: bool = False


class WriteResult(BaseModel):
    status: Literal["dry_run", "ok", "duplicate"]
    action: str
    marketplace: str
    preview: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    connects_cost: int | None = None
    connects_balance_after: int | None = None
    trace_id: str | None = None
