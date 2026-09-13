"""Schemas for releases, SOPs & checklists, knowledge, feedback, decisions, search."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from probelens.models.enums import (
    ChecklistStatus,
    DecisionStatus,
    FeedbackSentiment,
    FeedbackSource,
    FeedbackStatus,
    ReleaseStatus,
)
from probelens.schemas.auth import UserSummary

Platform = Literal["android", "ios", "web", "all"]


class EntityRef(BaseModel):
    """Enough to render a link to another object without a second request."""

    type: str
    id: int
    title: str
    status: str | None = None


class ReleaseEventOut(BaseModel):
    id: int
    occurred_at: datetime
    kind: str
    note: str
    actor: UserSummary | None

    model_config = {"from_attributes": True}


class ChecklistItem(BaseModel):
    key: str
    label: str
    owner_role: str | None = None
    done: bool = False
    owner_id: int | None = None
    done_at: datetime | None = None


class ChecklistOut(BaseModel):
    id: int
    sop_id: int | None
    release_id: int | None
    title: str
    owner: UserSummary
    status: ChecklistStatus
    items: list[ChecklistItem]
    done_count: int
    total_count: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChecklistProgress(BaseModel):
    done: int
    total: int


class ReleaseSummary(BaseModel):
    id: int
    version: str
    name: str
    platform: str
    status: ReleaseStatus
    release_date: date
    rollout_percent: int
    owner: UserSummary
    affected_areas: list[str]
    experiment_id: int | None
    checklist_progress: ChecklistProgress | None = None
    open_investigations: int = 0
    updated_at: datetime

    model_config = {"from_attributes": True}


class ImpactMetric(BaseModel):
    metric_key: str
    label: str
    format: str
    higher_is_better: bool
    before: float | None
    after: float | None
    abs_change: float | None
    rel_change: float | None
    formatted_before: str
    formatted_after: str
    formatted_change: str
    tone: Literal["good", "bad", "neutral", "unknown"]


class ReleaseImpact(BaseModel):
    before_start: date
    before_end: date
    after_start: date
    after_end: date
    scope: list[str]
    metrics: list[ImpactMetric]
    note: str


class ReleaseOut(ReleaseSummary):
    description: str
    timeline: list[ReleaseEventOut]
    checklists: list[ChecklistOut]
    investigations: list[EntityRef]
    decisions: list[EntityRef]
    experiment: EntityRef | None
    created_at: datetime


class ReleaseCreate(BaseModel):
    version: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=3, max_length=200)
    description: str = ""
    platform: Platform
    release_date: date
    affected_areas: list[str] = Field(default_factory=list)
    experiment_id: int | None = None
    sop_id: int | None = Field(default=None, description="Run this SOP as the launch checklist")


class ReleaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = None
    status: ReleaseStatus | None = None
    release_date: date | None = None
    rollout_percent: int | None = Field(default=None, ge=0, le=100)
    affected_areas: list[str] | None = None
    experiment_id: int | None = None
    note: str | None = Field(default=None, description="Timeline note explaining the change")


class ReleaseNoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=2000)
    kind: Literal["note", "link"] = "note"


class SopItem(BaseModel):
    key: str
    label: str
    owner_role: str | None = None


class SopOut(BaseModel):
    id: int
    title: str
    description: str
    category: str
    owner: UserSummary
    items: list[SopItem]
    run_count: int = 0
    updated_at: datetime

    model_config = {"from_attributes": True}


class SopCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = ""
    category: str = Field(min_length=2, max_length=60)
    items: list[SopItem] = Field(min_length=1)


class SopUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = None
    category: str | None = Field(default=None, min_length=2, max_length=60)
    items: list[SopItem] | None = None


class ChecklistCreate(BaseModel):
    sop_id: int
    release_id: int | None = None
    title: str | None = None


class ChecklistItemToggle(BaseModel):
    done: bool


class KnowledgeSummary(BaseModel):
    id: int
    title: str
    tags: list[str]
    author: UserSummary
    excerpt: str
    updated_at: datetime


class KnowledgeOut(BaseModel):
    id: int
    title: str
    body: str
    tags: list[str]
    author: UserSummary
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class KnowledgeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    body: str | None = Field(default=None, min_length=1)
    tags: list[str] | None = None


class StakeholderRef(BaseModel):
    id: int
    name: str
    team: str
    title: str

    model_config = {"from_attributes": True}


class FeedbackOut(BaseModel):
    id: int
    source: FeedbackSource
    theme: str
    body: str
    sentiment: FeedbackSentiment
    status: FeedbackStatus
    platform: str | None
    received_on: date
    stakeholder: StakeholderRef | None
    submitted_by: UserSummary
    linked: EntityRef | None
    created_at: datetime


class FeedbackCreate(BaseModel):
    source: FeedbackSource
    theme: str = Field(min_length=2, max_length=60)
    body: str = Field(min_length=3)
    sentiment: FeedbackSentiment = FeedbackSentiment.neutral
    platform: str | None = None
    received_on: date | None = None
    stakeholder_id: int | None = None
    linked_entity_type: str | None = None
    linked_entity_id: int | None = None


class FeedbackUpdate(BaseModel):
    status: FeedbackStatus | None = None
    theme: str | None = Field(default=None, min_length=2, max_length=60)
    sentiment: FeedbackSentiment | None = None
    linked_entity_type: str | None = None
    linked_entity_id: int | None = None
    unlink: bool | None = None


class ThemeSummary(BaseModel):
    theme: str
    total: int
    open: int
    negative: int
    last_received: date


class DecisionSummary(BaseModel):
    id: int
    title: str
    status: DecisionStatus
    owner: UserSummary
    decided_on: date
    follow_up_date: date | None
    follow_up_due: bool
    linked: list[EntityRef]
    decision: str
    updated_at: datetime


class DecisionOut(DecisionSummary):
    context: str
    evidence: str
    alternatives: str
    expected_impact: str
    investigation_id: int | None
    experiment_id: int | None
    release_id: int | None
    created_at: datetime


class DecisionCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    context: str = ""
    evidence: str = ""
    alternatives: str = ""
    decision: str = Field(min_length=3)
    expected_impact: str = ""
    status: DecisionStatus = DecisionStatus.decided
    decided_on: date | None = None
    follow_up_date: date | None = None
    investigation_id: int | None = None
    experiment_id: int | None = None
    release_id: int | None = None


class DecisionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    context: str | None = None
    evidence: str | None = None
    alternatives: str | None = None
    decision: str | None = Field(default=None, min_length=3)
    expected_impact: str | None = None
    status: DecisionStatus | None = None
    decided_on: date | None = None
    follow_up_date: date | None = None
    investigation_id: int | None = None
    experiment_id: int | None = None
    release_id: int | None = None


class SearchHit(BaseModel):
    type: str
    id: int
    title: str
    subtitle: str
    status: str | None = None
    rank: float
    updated_at: datetime | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    total: int
    groups: dict[str, list[SearchHit]]
