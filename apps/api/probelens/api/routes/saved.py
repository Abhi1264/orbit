from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from probelens.analytics.metrics import get_metric
from probelens.analytics.query import MetricQuery, run_metric_query
from probelens.api.deps import CurrentUser, DbSession, require
from probelens.core.errors import Forbidden, NotFound
from probelens.core.permissions import Permission
from probelens.models import SavedAnalysis, Segment
from probelens.models.enums import Role
from probelens.schemas.analytics_objects import (
    SavedAnalysisCreate,
    SavedAnalysisOut,
    SegmentCreate,
    SegmentMetric,
    SegmentOut,
    SegmentPreview,
    SegmentPreviewRequest,
)
from probelens.services.projects import default_project_id

router = APIRouter(tags=["saved"], dependencies=[Depends(require(Permission.run_analytics))])

SEGMENT_PREVIEW_METRICS = [
    "users",
    "sessions",
    "conversion",
    "checkout_conversion",
    "revenue",
    "aov",
    "payment_success_rate",
    "return_rate",
]


def _can_edit(user, owner_id: int) -> bool:
    return user.id == owner_id or user.role in (Role.admin, Role.pm)


@router.get("/saved-analyses", response_model=list[SavedAnalysisOut])
def list_saved(_: CurrentUser, db: DbSession) -> list[SavedAnalysis]:
    return list(
        db.scalars(
            select(SavedAnalysis)
            .options(selectinload(SavedAnalysis.owner))
            .order_by(SavedAnalysis.updated_at.desc())
        )
    )


@router.post("/saved-analyses", response_model=SavedAnalysisOut, status_code=201)
def create_saved(payload: SavedAnalysisCreate, user: CurrentUser, db: DbSession) -> SavedAnalysis:
    obj = SavedAnalysis(project_id=default_project_id(db), owner_id=user.id, **payload.model_dump())
    db.add(obj)
    db.flush()
    db.refresh(obj)
    return obj


@router.get("/saved-analyses/{analysis_id}", response_model=SavedAnalysisOut)
def get_saved(analysis_id: int, _: CurrentUser, db: DbSession) -> SavedAnalysis:
    obj = db.get(SavedAnalysis, analysis_id)
    if obj is None:
        raise NotFound("Analysis", analysis_id)
    return obj


@router.delete("/saved-analyses/{analysis_id}", status_code=204)
def delete_saved(analysis_id: int, user: CurrentUser, db: DbSession) -> None:
    obj = db.get(SavedAnalysis, analysis_id)
    if obj is None:
        raise NotFound("Analysis", analysis_id)
    if not _can_edit(user, obj.owner_id):
        raise Forbidden()
    db.delete(obj)


@router.get("/segments", response_model=list[SegmentOut])
def list_segments(_: CurrentUser, db: DbSession) -> list[Segment]:
    return list(db.scalars(select(Segment).options(selectinload(Segment.owner)).order_by(Segment.name)))


@router.post("/segments", response_model=SegmentOut, status_code=201)
def create_segment(payload: SegmentCreate, user: CurrentUser, db: DbSession) -> Segment:
    obj = Segment(
        project_id=default_project_id(db),
        owner_id=user.id,
        name=payload.name,
        description=payload.description,
        conditions=[c.model_dump(exclude_none=True) for c in payload.conditions],
    )
    db.add(obj)
    db.flush()
    db.refresh(obj)
    return obj


@router.put("/segments/{segment_id}", response_model=SegmentOut)
def update_segment(segment_id: int, payload: SegmentCreate, user: CurrentUser, db: DbSession) -> Segment:
    obj = db.get(Segment, segment_id)
    if obj is None:
        raise NotFound("Segment", segment_id)
    if not _can_edit(user, obj.owner_id):
        raise Forbidden()
    obj.name = payload.name
    obj.description = payload.description
    obj.conditions = [c.model_dump(exclude_none=True) for c in payload.conditions]
    db.flush()
    return obj


@router.delete("/segments/{segment_id}", status_code=204)
def delete_segment(segment_id: int, user: CurrentUser, db: DbSession) -> None:
    obj = db.get(Segment, segment_id)
    if obj is None:
        raise NotFound("Segment", segment_id)
    if not _can_edit(user, obj.owner_id):
        raise Forbidden()
    db.delete(obj)


@router.post("/segments/preview", response_model=SegmentPreview)
def preview_segment(payload: SegmentPreviewRequest) -> SegmentPreview:
    metrics: list[SegmentMetric] = []
    for key in SEGMENT_PREVIEW_METRICS:
        m = get_metric(key)
        seg = run_metric_query(
            MetricQuery(
                metric=key,
                date_from=payload.date_from,
                date_to=payload.date_to,
                filters=payload.conditions,
                granularity=None,
                compare_from=payload.compare_from,
                compare_to=payload.compare_to,
            )
        ).series[0]
        base = run_metric_query(
            MetricQuery(metric=key, date_from=payload.date_from, date_to=payload.date_to, granularity=None)
        ).series[0]
        metrics.append(
            SegmentMetric(
                key=key,
                label=m.label,
                format=m.format.value,
                value=seg.total.value,
                compare_value=seg.compare_total.value if seg.compare_total else None,
                baseline_value=base.total.value,
            )
        )
    return SegmentPreview(conditions=[c.describe() for c in payload.conditions], metrics=metrics)
