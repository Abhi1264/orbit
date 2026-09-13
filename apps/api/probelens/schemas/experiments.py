from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from probelens.analytics.dimensions import Filter
from probelens.models.enums import ExperimentDecision, ExperimentStatus
from probelens.schemas.auth import UserSummary

class VariantIn(BaseModel):
    key: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    weight: int = Field(default=50, ge=1, le=100)
    is_control: bool = False

class VariantOut(VariantIn):
    id: int

    model_config = {"from_attributes": True}

class ExperimentBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    hypothesis: str = Field(min_length=1)
    description: str = ""
    primary_metric: str
    guardrail_metrics: list[str] = Field(default_factory=list, max_length=6)
    audience_filters: list[Filter] = Field(default_factory=list, max_length=8)
    traffic_percent: int = Field(default=100, ge=1, le=100)
    min_sample_per_variant: int = Field(default=2000, ge=100)
    min_relative_effect: float = Field(default=0.02, gt=0, le=1)
    min_duration_days: int = Field(default=7, ge=1, le=90)
    start_date: date | None = None
    end_date: date | None = None

class ExperimentCreate(ExperimentBase):
    key: str | None = Field(default=None, min_length=2, max_length=60, pattern=r"^[a-z0-9_]+$")
    variants: list[VariantIn] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def _check(self) -> "ExperimentCreate":
        keys = [v.key for v in self.variants]
        if len(set(keys)) != len(keys):
            raise ValueError("Variant keys must be unique")
        if sum(v.is_control for v in self.variants) != 1:
            raise ValueError("Exactly one variant must be the control")
        if self.primary_metric in self.guardrail_metrics:
            raise ValueError("A metric cannot be both primary and guardrail")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("End date must be on or after the start date")
        return self

class ExperimentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    hypothesis: str | None = None
    description: str | None = None
    status: ExperimentStatus | None = None
    primary_metric: str | None = None
    guardrail_metrics: list[str] | None = Field(default=None, max_length=6)
    audience_filters: list[Filter] | None = Field(default=None, max_length=8)
    traffic_percent: int | None = Field(default=None, ge=1, le=100)
    min_sample_per_variant: int | None = Field(default=None, ge=100)
    min_relative_effect: float | None = Field(default=None, gt=0, le=1)
    min_duration_days: int | None = Field(default=None, ge=1, le=90)
    start_date: date | None = None
    end_date: date | None = None
    variants: list[VariantIn] | None = Field(default=None, min_length=2, max_length=5)

class ExperimentSummary(BaseModel):
    id: int
    key: str
    name: str
    status: ExperimentStatus
    owner: UserSummary
    start_date: date
    end_date: date | None
    primary_metric: str
    primary_metric_label: str
    guardrail_metrics: list[str]
    traffic_percent: int
    variant_count: int
    decision: ExperimentDecision | None
    has_exposure_events: bool
    updated_at: datetime

class ExperimentOut(ExperimentSummary):
    hypothesis: str
    description: str
    audience_filters: list[Filter]
    filter_labels: list[str]
    min_sample_per_variant: int
    min_relative_effect: float
    min_duration_days: int
    variants: list[VariantOut]
    decision_reason: str
    decided_at: datetime | None
    decided_by: UserSummary | None
    created_at: datetime

class DecisionIn(BaseModel):
    decision: ExperimentDecision
    reason: str = Field(min_length=1)
    # Also record it in the decision log; on by default because that is the point.
    log: bool = True

class MemoOut(BaseModel):
    markdown: str
    as_of: date
