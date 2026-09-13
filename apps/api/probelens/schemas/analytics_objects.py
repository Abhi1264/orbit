from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from probelens.analytics.dimensions import Filter
from probelens.schemas.auth import UserSummary


class SavedAnalysisCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    kind: Literal["analysis", "funnel", "cohort"]
    config: dict[str, Any]


class SavedAnalysisOut(SavedAnalysisCreate):
    id: int
    owner: UserSummary
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SegmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    conditions: list[Filter] = Field(min_length=1, max_length=8)


class SegmentOut(BaseModel):
    id: int
    name: str
    description: str
    conditions: list[Filter]
    owner: UserSummary
    created_at: datetime

    model_config = {"from_attributes": True}


class SegmentPreviewRequest(BaseModel):
    conditions: list[Filter] = Field(default_factory=list, max_length=8)
    date_from: date
    date_to: date
    compare_from: date | None = None
    compare_to: date | None = None


class SegmentMetric(BaseModel):
    key: str
    label: str
    format: str
    value: float | None
    compare_value: float | None = None
    baseline_value: float | None = None  # same metric, all sessions, same period


class SegmentPreview(BaseModel):
    conditions: list[str]
    metrics: list[SegmentMetric]
