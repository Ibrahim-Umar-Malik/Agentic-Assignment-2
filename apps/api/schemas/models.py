"""Request and response models: the typed API contract the TypeScript client is generated from."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=6, max_length=200)


class RegisterIn(LoginIn):
    name: str = Field(default="", max_length=100)
    persona: Literal["ai_ml", "fullstack", "data_analyst"] = "ai_ml"


class SessionOut(BaseModel):
    token: str
    user: UserOut


class UserOut(BaseModel):
    id: str
    email: str
    name: str | None = None
    persona: str | None = None
    settings: dict[str, Any] = {}


class SettingsIn(BaseModel):
    persona: Literal["ai_ml", "fullstack", "data_analyst"] | None = None
    hourly_floor: float | None = Field(default=None, ge=0, le=1000)
    weekly_connects_budget: int | None = Field(default=None, ge=0, le=1000)
    hours_per_week: int | None = Field(default=None, ge=1, le=80)
    autonomy: Literal["suggest", "auto_skip_low_fit"] | None = None
    marketplace: Literal["gigsim", "upwork_live"] | None = None
    categories: list[str] | None = None
    min_budget: float | None = None
    onboarded: bool | None = None


class SearchIn(BaseModel):
    query: str = Field(default="", max_length=200)
    category: str | None = None
    interval_min: int = Field(default=30, ge=5, le=1440)


class SearchOut(SearchIn):
    id: str
    last_run: float | None = None


class JobCard(BaseModel):
    job_id: str
    title: str
    category: str | None = None
    budget: float | None = None
    budget_type: str | None = None
    status: str
    action: str | None = None
    fit: float | None = None
    risk: float | None = None
    price: float | None = None
    connects: int | None = None
    risk_flags: list[str] = []
    posted_at: str | None = None
    has_approval: bool = False


class JobDetail(BaseModel):
    job: dict[str, Any]
    status: str
    thread_id: str | None = None
    spec: dict[str, Any] | None = None
    risk: dict[str, Any] | None = None
    fit: dict[str, Any] | None = None
    decision: dict[str, Any] | None = None
    price: dict[str, Any] | None = None
    draft: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    critiques: list[dict[str, Any]] = []
    compliance: dict[str, Any] | None = None
    submission: dict[str, Any] | None = None
    node_log: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    approval_id: str | None = None


class ApprovalOut(BaseModel):
    id: str
    thread_id: str
    graph: str
    kind: str | None
    job_id: str | None
    status: str
    payload: dict[str, Any]
    created_at: float


class DecisionIn(BaseModel):
    action: Literal["approve", "edit", "reject", "regenerate"]
    cover_letter: str | None = Field(default=None, max_length=5000)
    body: str | None = Field(default=None, max_length=5000)
    screening_answers: list[dict[str, str]] | None = None
    reason: str | None = Field(default=None, max_length=500)
    paragraph: int | None = Field(default=None, ge=0, le=20)
    instruction: str | None = Field(default=None, max_length=300)
    slot: int | None = Field(default=None, ge=0, le=5)


class RunRef(BaseModel):
    run_id: str | None = None
    status: str
    detail: str | None = None


class RunOut(BaseModel):
    id: str
    graph: str
    thread_id: str
    job_id: str | None
    status: str
    trace_id: str | None
    started_at: float
    finished_at: float | None
    tokens: int | None
    cost_usd: float | None
    error: str | None = None


class TraceOut(BaseModel):
    trace_id: str
    spans: list[dict[str, Any]]
    totals: dict[str, Any]


class PipelineCard(BaseModel):
    job_id: str
    title: str | None
    stage: str
    bid: float | None
    connects: int | None
    category: str | None
    thread_id: str | None
    updated_at: float | None


class HealthOut(BaseModel):
    ok: bool
    marketplace: dict[str, Any]
    services: dict[str, Any]
    mode: str
    profile: str


class MemoryItem(BaseModel):
    namespace: list[str]
    key: str
    rule: str | None = None
    value: dict[str, Any] = {}


class PortfolioItem(BaseModel):
    id: str
    type: str | None
    title: str | None
    project: str | None
    date: str | None
    deleted: bool = False


SessionOut.model_rebuild()
