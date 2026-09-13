from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from probelens.analytics.dimensions import Filter
from probelens.models.enums import (
    ActionStatus,
    AnomalyStatus,
    Confidence,
    FindingKind,
    HypothesisState,
    InvestigationStatus,
)
from probelens.schemas.auth import UserSummary

# --------------------------------------------------------------------------- anomalies


class AnomalyOut(BaseModel):
    id: int
    metric_key: str
    metric_label: str
    metric_format: str
    higher_is_better: bool
    filters: list[Filter]
    filter_labels: list[str]
    period_start: date
    period_end: date
    ongoing: bool
    expected: float
    actual: float
    zscore: float
    direction: str
    severity: str
    status: AnomalyStatus
    investigation_id: int | None
    detected_at: datetime

    model_config = {"from_attributes": True}


class AnomalyUpdate(BaseModel):
    status: AnomalyStatus


class DetectionSummary(BaseModel):
    as_of: date
    detected: int
    created: int
    updated: int


# --------------------------------------------------------------------------- investigations


class StakeholderOut(BaseModel):
    id: int
    name: str
    email: str
    team: str
    title: str

    model_config = {"from_attributes": True}


class InvestigationStakeholderOut(BaseModel):
    stakeholder: StakeholderOut
    role: str

    model_config = {"from_attributes": True}


class FindingCreate(BaseModel):
    kind: FindingKind
    title: str = Field(min_length=1, max_length=300)
    body: str = ""
    confidence: Confidence | None = None
    state: HypothesisState | None = None
    data: dict[str, Any] | None = None


class FindingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    body: str | None = None
    confidence: Confidence | None = None
    state: HypothesisState | None = None


class FindingOut(BaseModel):
    id: int
    kind: FindingKind
    title: str
    body: str
    confidence: Confidence | None
    state: HypothesisState | None
    data: dict[str, Any] | None
    source: str
    author: UserSummary | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ActionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    owner_id: int | None = None
    due_date: date | None = None


class ActionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    owner_id: int | None = None
    status: ActionStatus | None = None
    due_date: date | None = None


class ActionOut(BaseModel):
    id: int
    title: str
    owner: UserSummary | None
    status: ActionStatus
    due_date: date | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InvestigationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    metric_key: str
    filters: list[Filter] = Field(default_factory=list, max_length=8)
    period_start: date
    period_end: date
    baseline_start: date
    baseline_end: date
    observation: str = ""
    anomaly_id: int | None = None
    release_id: int | None = None
    experiment_id: int | None = None


class InvestigationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: InvestigationStatus | None = None
    owner_id: int | None = None
    observation: str | None = None
    decision: str | None = None
    release_id: int | None = None
    experiment_id: int | None = None
    baseline_start: date | None = None
    baseline_end: date | None = None


class StakeholderAssignment(BaseModel):
    stakeholder_id: int
    role: str = "informed"


class LinkedRelease(BaseModel):
    id: int
    version: str
    name: str
    platform: str
    release_date: date
    status: str

    model_config = {"from_attributes": True}


class LinkedExperiment(BaseModel):
    id: int
    key: str
    name: str
    status: str
    primary_metric: str

    model_config = {"from_attributes": True}


class InvestigationSummary(BaseModel):
    id: int
    title: str
    status: InvestigationStatus
    owner: UserSummary
    metric_key: str
    metric_label: str
    filters: list[Filter]
    filter_labels: list[str]
    period_start: date
    period_end: date
    finding_counts: dict[str, int]
    open_actions: int
    updated_at: datetime
    created_at: datetime


class InvestigationOut(InvestigationSummary):
    baseline_start: date
    baseline_end: date
    observation: str
    decision: str
    resolved_at: datetime | None
    findings: list[FindingOut]
    actions: list[ActionOut]
    stakeholders: list[InvestigationStakeholderOut]
    anomaly: AnomalyOut | None
    release: LinkedRelease | None
    experiment: LinkedExperiment | None


# --------------------------------------------------------------------------- comments


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class CommentOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    author: UserSummary
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}
