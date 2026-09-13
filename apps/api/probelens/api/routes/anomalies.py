from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from probelens.analytics.anomalies import run_detection
from probelens.analytics.dimensions import Filter
from probelens.analytics.meta import get_meta
from probelens.analytics.metrics import get_metric
from probelens.api.deps import CurrentUser, DbSession, require
from probelens.core.errors import NotFound
from probelens.core.permissions import Permission
from probelens.models import Anomaly
from probelens.models.enums import AnomalyStatus
from probelens.schemas.investigations import AnomalyOut, AnomalyUpdate, DetectionSummary
from probelens.services.projects import default_project_id

router = APIRouter(tags=["anomalies"], dependencies=[Depends(require(Permission.run_analytics))])

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def anomaly_out(a: Anomaly, data_end: date | None) -> AnomalyOut:
    m = get_metric(a.metric_key)
    filters = [Filter.model_validate(f) for f in a.filters]
    return AnomalyOut(
        id=a.id,
        metric_key=a.metric_key,
        metric_label=m.label,
        metric_format=m.format.value,
        higher_is_better=m.higher_is_better,
        filters=filters,
        filter_labels=[f.describe() for f in filters],
        period_start=a.period_start,
        period_end=a.period_end,
        ongoing=data_end is not None and a.period_end >= data_end,
        expected=a.expected,
        actual=a.actual,
        zscore=a.zscore,
        direction=a.direction,
        severity=a.severity,
        status=AnomalyStatus(a.status),
        investigation_id=a.investigation_id,
        detected_at=a.detected_at,
    )


@router.get("/anomalies", response_model=list[AnomalyOut])
def list_anomalies(
    _: CurrentUser,
    db: DbSession,
    status: AnomalyStatus | None = None,
    metric: str | None = None,
    severity: str | None = Query(default=None, pattern="^(low|medium|high)$"),
) -> list[AnomalyOut]:
    stmt = select(Anomaly)
    if status:
        stmt = stmt.where(Anomaly.status == status.value)
    if metric:
        stmt = stmt.where(Anomaly.metric_key == metric)
    if severity:
        stmt = stmt.where(Anomaly.severity == severity)
    rows = list(db.scalars(stmt))
    data_end = get_meta().data_end
    out = [anomaly_out(a, data_end) for a in rows]
    # Ongoing, severe and recent first: that is the triage order.
    out.sort(key=lambda a: (not a.ongoing, SEVERITY_ORDER[a.severity], -abs(a.zscore)))
    return out


@router.get("/anomalies/{anomaly_id}", response_model=AnomalyOut)
def get_anomaly(anomaly_id: int, _: CurrentUser, db: DbSession) -> AnomalyOut:
    a = db.get(Anomaly, anomaly_id)
    if a is None:
        raise NotFound("Anomaly", anomaly_id)
    return anomaly_out(a, get_meta().data_end)


@router.patch("/anomalies/{anomaly_id}", response_model=AnomalyOut)
def update_anomaly(
    anomaly_id: int,
    payload: AnomalyUpdate,
    _: CurrentUser,
    db: DbSession,
) -> AnomalyOut:
    a = db.get(Anomaly, anomaly_id)
    if a is None:
        raise NotFound("Anomaly", anomaly_id)
    a.status = payload.status.value
    db.flush()
    return anomaly_out(a, get_meta().data_end)


@router.post(
    "/anomalies/detect",
    response_model=DetectionSummary,
    dependencies=[Depends(require(Permission.manage_investigations))],
)
def detect_now(_: CurrentUser, db: DbSession) -> DetectionSummary:
    """Run the detector against the dataset's last day. The worker does this on a
    schedule; this endpoint exists so a demo never depends on the scheduler."""
    as_of = get_meta().data_end or date.today()
    summary = run_detection(db, default_project_id(db), as_of, datetime.now(UTC))
    return DetectionSummary(as_of=as_of, **summary)
