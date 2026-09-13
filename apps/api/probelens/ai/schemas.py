"""Wire format for the analyst: what a question looks like and what an answer is.

The answer is structured on purpose. A paragraph of prose cannot be checked;
a list of facts each pointing at the tool call that produced it can.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from probelens.analytics.dimensions import Filter

Mode = Literal["llm", "demo"]
Confidence = Literal["low", "medium", "high"]


class AskContext(BaseModel):
    """Where the user is asking from; lets the analyst default sensibly."""

    date_from: date | None = None
    date_to: date | None = None
    metric: str | None = None
    filters: list[Filter] = Field(default_factory=list)
    investigation_id: int | None = None
    experiment_id: int | None = None


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    context: AskContext = Field(default_factory=AskContext)
    # Force demo mode even when an LLM is configured (used by tests and the acceptance run).
    mode: Mode | None = None


class ToolCallRecord(BaseModel):
    id: str
    name: str
    args: dict[str, Any]
    summary: str  # one line, human-readable, what came back
    ms: int
    error: str | None = None
    data: dict[str, Any] | None = None  # full result, for the evidence drawer


class Fact(BaseModel):
    text: str
    source: str  # tool call id


class Inference(BaseModel):
    text: str
    confidence: Confidence
    basis: list[str] = Field(default_factory=list)  # tool call ids


class RecommendationItem(BaseModel):
    text: str
    priority: Literal["now", "next", "later"] = "next"


class CandidateOut(BaseModel):
    title: str
    confidence: Confidence
    evidence: str
    kind: str = "segment"
    href: str | None = None


class LinkOut(BaseModel):
    label: str
    href: str


class AnalystAnswer(BaseModel):
    summary: str
    facts: list[Fact] = Field(default_factory=list)
    inferences: list[Inference] = Field(default_factory=list)
    candidates: list[CandidateOut] = Field(default_factory=list)
    recommendations: list[RecommendationItem] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list)
    links: list[LinkOut] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class AskResponse(BaseModel):
    run_id: int
    mode: Mode
    model: str
    question: str
    answer: AnalystAnswer
    tool_calls: list[ToolCallRecord]
    latency_ms: int
    created_at: datetime


class AiRunSummary(BaseModel):
    id: int
    question: str
    mode: Mode
    model: str
    summary: str
    tool_count: int
    latency_ms: int
    error: str
    created_at: datetime


class PlanRequest(BaseModel):
    text: str = Field(min_length=2, max_length=500)
    context: AskContext = Field(default_factory=AskContext)


class PlannedQuery(BaseModel):
    metric: str
    date_from: date
    date_to: date
    filters: list[Filter] = Field(default_factory=list)
    breakdown: str | None = None
    granularity: Literal["hour", "day", "week", "month"] = "day"
    compare_from: date | None = None
    compare_to: date | None = None


class PlanResponse(BaseModel):
    query: PlannedQuery
    explanation: str  # "Conversion rate, Android, 1–13 Sep, by traffic source, vs previous 13 days"
    confidence: Confidence
    unresolved: list[str] = Field(default_factory=list)  # words we could not map
    mode: Mode


class Suggestion(BaseModel):
    text: str
    kind: Literal["why", "what", "funnel", "experiment", "attention"]
