"""Structured hand-offs (C3). Agents exchange these Pydantic objects, never free text, for anything a later
step decides on."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Requirement(BaseModel):
    text: str
    skill: str | None = None
    must_have: bool = True


class JobSpec(BaseModel):
    job_id: str
    title: str
    category: str | None = None
    deliverables: list[str] = []
    requirements: list[Requirement] = []
    budget_type: Literal["fixed", "hourly"] | None = None
    budget: float | None = None
    timeline: str | None = None
    screening_questions: list[str] = []
    hidden_needs: list[str] = Field(default_factory=list, description="Needs the client implies but does not state")
    vague: bool = False


class RiskFlag(BaseModel):
    kind: Literal["scam", "free_work", "off_platform", "contact_harvest", "advance_fee", "injection", "unverified_payment",
                  "new_client", "low_budget", "duplicate", "other"]
    severity: float = Field(ge=0, le=1)
    evidence: str = ""


class RiskReport(BaseModel):
    risk_score: float = Field(ge=0, le=1)
    client_quality: float = Field(ge=0, le=1)
    flags: list[RiskFlag] = []
    injection_detected: bool = False
    scam: bool = False
    summary: str = ""


class EvidenceRef(BaseModel):
    item_id: str
    project: str | None = None
    type: str | None = None
    title: str | None = None
    snippet: str = ""
    score: float = 0.0
    outcome: str | None = None


class RequirementMatch(BaseModel):
    requirement: str
    coverage: Literal["full", "partial", "none"]
    evidence: list[EvidenceRef] = []


class FitReport(BaseModel):
    fit_score: float = Field(ge=0, le=1)
    matrix: list[RequirementMatch] = []
    reasons: list[str] = []
    unsupported_requirements: list[str] = []
    top_projects: list[str] = []


class BidDecision(BaseModel):
    action: Literal["skip", "watch", "bid"]
    reasons: list[str] = []
    fit: float = 0.0
    risk: float = 0.0


class PriceQuote(BaseModel):
    amount: float
    budget_type: Literal["fixed", "hourly"]
    rationale: str
    market: dict = {}
    floor: float = 0.0
    connects_cost: int = 0
    connects_usd: float = 0.0
    expected_value_usd: float = 0.0
    worth_connects: bool = True


class ScreeningAnswer(BaseModel):
    question: str
    answer: str


class ClaimRef(BaseModel):
    text: str
    label: Literal["supported", "partly_supported", "unsupported"]
    evidence_ids: list[str] = []
    score: float = 0.0


class ProposalDraft(BaseModel):
    cover_letter: str
    screening_answers: list[ScreeningAnswer] = []
    claims: list[ClaimRef] = []
    version: int = 1
    strategy: str = "evidence_first"
    cited_items: list[str] = []


class CritiqueIssue(BaseModel):
    kind: Literal["grounding", "personalisation", "length", "generic_opening", "screening", "tone", "other"]
    detail: str
    paragraph: int | None = None


class Critique(BaseModel):
    score: float = Field(ge=0, le=1)
    approve: bool
    issues: list[CritiqueIssue] = []
    revision_instructions: str = ""


class ComplianceViolation(BaseModel):
    rule_id: str
    detail: str
    action: Literal["redact", "rewrite", "block"]


class ComplianceVerdict(BaseModel):
    status: Literal["pass", "fixed", "block"]
    violations: list[ComplianceViolation] = []
    cleaned_text: str = ""
    cleaned_answers: list[ScreeningAnswer] = []
    policy_version: int | str = 1


class MessageIntent(BaseModel):
    intent: Literal["question", "negotiation", "interview_request", "scam_signal", "other"]
    confidence: float = Field(ge=0, le=1)
    summary: str = ""
    requested_rate: float | None = None


class ReplyDraft(BaseModel):
    body: str
    proposed_slots: list[dict] = []
    walk_away: bool = False
    version: int = 1
