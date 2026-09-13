from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from probelens.analytics.dimensions import Filter
from probelens.analytics.meta import get_meta
from probelens.analytics.metrics import METRICS, format_value, get_metric
from probelens.analytics.rootcause import RootCauseAnalysis, analyze
from probelens.api.deps import CurrentUser, DbSession, require
from probelens.api.routes.anomalies import anomaly_out
from probelens.core.errors import BadRequest, Forbidden, NotFound
from probelens.core.permissions import Permission, has_permission
from probelens.models import (
    Anomaly,
    Experiment,
    Investigation,
    InvestigationAction,
    InvestigationFinding,
    InvestigationStakeholder,
    Release,
    Stakeholder,
    User,
)
from probelens.models.enums import (
    AnomalyStatus,
    FindingKind,
    HypothesisState,
    InvestigationStatus,
    Role,
)
from probelens.schemas.investigations import (
    ActionCreate,
    ActionOut,
    ActionUpdate,
    FindingCreate,
    FindingOut,
    FindingUpdate,
    InvestigationCreate,
    InvestigationOut,
    InvestigationSummary,
    InvestigationUpdate,
    StakeholderAssignment,
    StakeholderOut,
)
from probelens.services.projects import default_project_id

router = APIRouter(tags=["investigations"], dependencies=[Depends(require(Permission.view))])

_write = Depends(require(Permission.manage_investigations))

def _load(db: Session, investigation_id: int) -> Investigation:
    inv = db.get(
        Investigation,
        investigation_id,
        options=[
            selectinload(Investigation.owner),
            selectinload(Investigation.findings).selectinload(InvestigationFinding.author),
            selectinload(Investigation.actions).selectinload(InvestigationAction.owner),
            selectinload(Investigation.stakeholders).selectinload(InvestigationStakeholder.stakeholder),
        ],
    )
    if inv is None:
        raise NotFound("Investigation", investigation_id)
    return inv

def _can_edit(user: User, inv: Investigation) -> bool:
    if user.role in (Role.admin, Role.pm):
        return True
    return has_permission(user.role, Permission.manage_investigations) and (
        user.id == inv.owner_id or user.role == Role.analyst
    )

def _summary_fields(inv: Investigation) -> dict:
    filters = [Filter.model_validate(f) for f in inv.filters or []]
    counts: dict[str, int] = {k.value: 0 for k in FindingKind}
    for f in inv.findings:
        counts[f.kind.value] += 1
    return {
        "id": inv.id,
        "title": inv.title,
        "status": inv.status,
        "owner": inv.owner,
        "metric_key": inv.metric_key,
        "metric_label": METRICS[inv.metric_key].label if inv.metric_key in METRICS else inv.metric_key,
        "filters": filters,
        "filter_labels": [f.describe() for f in filters],
        "period_start": inv.period_start,
        "period_end": inv.period_end,
        "finding_counts": counts,
        "open_actions": sum(1 for a in inv.actions if a.status.value != "done"),
        "updated_at": inv.updated_at,
        "created_at": inv.created_at,
    }

def _to_out(db: Session, inv: Investigation) -> InvestigationOut:
    anomaly = db.scalar(select(Anomaly).where(Anomaly.investigation_id == inv.id).limit(1))
    release = db.get(Release, inv.release_id) if inv.release_id else None
    experiment = db.get(Experiment, inv.experiment_id) if inv.experiment_id else None
    return InvestigationOut(
        **_summary_fields(inv),
        baseline_start=inv.baseline_start,
        baseline_end=inv.baseline_end,
        observation=inv.observation,
        decision=inv.decision,
        resolved_at=inv.resolved_at,
        findings=[FindingOut.model_validate(f) for f in inv.findings],
        actions=[ActionOut.model_validate(a) for a in inv.actions],
        stakeholders=inv.stakeholders,
        anomaly=anomaly_out(anomaly, get_meta().data_end) if anomaly else None,
        release=release,
        experiment=experiment,
    )

@router.get("/investigations", response_model=list[InvestigationSummary])
def list_investigations(
    _: CurrentUser, db: DbSession, status: InvestigationStatus | None = None
) -> list[InvestigationSummary]:
    stmt = (
        select(Investigation)
        .options(
            selectinload(Investigation.owner),
            selectinload(Investigation.findings),
            selectinload(Investigation.actions),
        )
        .order_by(Investigation.updated_at.desc())
    )
    if status:
        stmt = stmt.where(Investigation.status == status)
    return [InvestigationSummary(**_summary_fields(inv)) for inv in db.scalars(stmt)]

@router.post("/investigations", response_model=InvestigationOut, status_code=201, dependencies=[_write])
def create_investigation(payload: InvestigationCreate, user: CurrentUser, db: DbSession) -> InvestigationOut:
    if payload.metric_key not in METRICS:
        raise BadRequest(f"Unknown metric '{payload.metric_key}'")
    if payload.period_start > payload.period_end or payload.baseline_start > payload.baseline_end:
        raise BadRequest("Window start must be on or before its end")

    inv = Investigation(
        project_id=default_project_id(db),
        title=payload.title,
        status=InvestigationStatus.open,
        owner_id=user.id,
        metric_key=payload.metric_key,
        filters=[f.model_dump(exclude_none=True) for f in payload.filters],
        period_start=payload.period_start,
        period_end=payload.period_end,
        baseline_start=payload.baseline_start,
        baseline_end=payload.baseline_end,
        observation=payload.observation,
        release_id=payload.release_id,
        experiment_id=payload.experiment_id,
    )
    db.add(inv)
    db.flush()

    if payload.anomaly_id is not None:
        anomaly = db.get(Anomaly, payload.anomaly_id)
        if anomaly is None:
            raise NotFound("Anomaly", payload.anomaly_id)
        anomaly.investigation_id = inv.id
        anomaly.status = AnomalyStatus.investigating.value
        m = get_metric(anomaly.metric_key)
        inv.status = InvestigationStatus.investigating
        # The detector's numbers become the first, system-authored observation so
        # the trail starts from what was actually measured.
        db.add(
            InvestigationFinding(
                investigation_id=inv.id,
                kind=FindingKind.observation,
                title=(
                    f"{m.label} {'rose' if anomaly.direction == 'up' else 'fell'} to "
                    f"{format_value(m.format, anomaly.actual)} against an expected "
                    f"{format_value(m.format, anomaly.expected)}"
                ),
                body=(
                    f"Detected by the anomaly monitor: robust z-score {anomaly.zscore:+.1f} over "
                    f"{anomaly.period_start:%d %b}–{anomaly.period_end:%d %b}"
                    + (
                        f" within {', '.join(Filter.model_validate(f).describe() for f in anomaly.filters)}."
                        if anomaly.filters
                        else " store-wide."
                    )
                ),
                data={
                    "anomaly_id": anomaly.id,
                    "expected": anomaly.expected,
                    "actual": anomaly.actual,
                    "zscore": anomaly.zscore,
                    "severity": anomaly.severity,
                },
                source="system",
                author_id=None,
            )
        )
        db.flush()

    return _to_out(db, _load(db, inv.id))

@router.get("/investigations/{investigation_id}", response_model=InvestigationOut)
def get_investigation(investigation_id: int, _: CurrentUser, db: DbSession) -> InvestigationOut:
    return _to_out(db, _load(db, investigation_id))

@router.patch("/investigations/{investigation_id}", response_model=InvestigationOut, dependencies=[_write])
def update_investigation(
    investigation_id: int, payload: InvestigationUpdate, user: CurrentUser, db: DbSession
) -> InvestigationOut:
    inv = _load(db, investigation_id)
    if not _can_edit(user, inv):
        raise Forbidden()
    changes = payload.model_dump(exclude_unset=True)
    if (
        "owner_id" in changes
        and changes["owner_id"] is not None
        and db.get(User, changes["owner_id"]) is None
    ):
        raise NotFound("User", changes["owner_id"])
    for key, value in changes.items():
        setattr(inv, key, value)
    if "status" in changes:
        if inv.status in (InvestigationStatus.resolved, InvestigationStatus.closed):
            inv.resolved_at = inv.resolved_at or datetime.now(UTC)
            for anomaly in db.scalars(select(Anomaly).where(Anomaly.investigation_id == inv.id)):
                anomaly.status = AnomalyStatus.resolved.value
        else:
            inv.resolved_at = None
    db.flush()
    db.expire(inv)
    return _to_out(db, _load(db, investigation_id))

@router.delete("/investigations/{investigation_id}", status_code=204, dependencies=[_write])
def delete_investigation(investigation_id: int, user: CurrentUser, db: DbSession) -> None:
    inv = _load(db, investigation_id)
    if user.role not in (Role.admin, Role.pm) and user.id != inv.owner_id:
        raise Forbidden()
    for anomaly in db.scalars(select(Anomaly).where(Anomaly.investigation_id == inv.id)):
        anomaly.investigation_id = None
        if anomaly.status == AnomalyStatus.investigating.value:
            anomaly.status = AnomalyStatus.open.value
    db.delete(inv)

@router.post(
    "/investigations/{investigation_id}/findings",
    response_model=FindingOut,
    status_code=201,
    dependencies=[_write],
)
def add_finding(
    investigation_id: int, payload: FindingCreate, user: CurrentUser, db: DbSession
) -> InvestigationFinding:
    inv = _load(db, investigation_id)
    if not _can_edit(user, inv):
        raise Forbidden()
    is_hypothesis = payload.kind == FindingKind.hypothesis
    state = (payload.state or HypothesisState.proposed) if is_hypothesis else None
    finding = InvestigationFinding(
        investigation_id=inv.id,
        kind=payload.kind,
        title=payload.title,
        body=payload.body,
        confidence=payload.confidence,
        state=state,
        data=payload.data,
        source="user",
        author_id=user.id,
    )
    db.add(finding)
    if inv.status == InvestigationStatus.open:
        inv.status = InvestigationStatus.investigating
    db.flush()
    db.refresh(finding)
    return finding

@router.patch(
    "/investigations/{investigation_id}/findings/{finding_id}",
    response_model=FindingOut,
    dependencies=[_write],
)
def update_finding(
    investigation_id: int, finding_id: int, payload: FindingUpdate, user: CurrentUser, db: DbSession
) -> InvestigationFinding:
    inv = _load(db, investigation_id)
    if not _can_edit(user, inv):
        raise Forbidden()
    finding = next((f for f in inv.findings if f.id == finding_id), None)
    if finding is None:
        raise NotFound("Finding", finding_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(finding, key, value)
    # Marking a hypothesis supported or refuted is the "validating" step of the workflow.
    if (
        finding.kind == FindingKind.hypothesis
        and finding.state in (HypothesisState.supported, HypothesisState.refuted)
        and inv.status == InvestigationStatus.investigating
    ):
        inv.status = InvestigationStatus.validating
    db.flush()
    db.refresh(finding)
    return finding

@router.delete(
    "/investigations/{investigation_id}/findings/{finding_id}", status_code=204, dependencies=[_write]
)
def delete_finding(investigation_id: int, finding_id: int, user: CurrentUser, db: DbSession) -> None:
    inv = _load(db, investigation_id)
    if not _can_edit(user, inv):
        raise Forbidden()
    finding = next((f for f in inv.findings if f.id == finding_id), None)
    if finding is None:
        raise NotFound("Finding", finding_id)
    db.delete(finding)

@router.post(
    "/investigations/{investigation_id}/actions",
    response_model=ActionOut,
    status_code=201,
    dependencies=[_write],
)
def add_action(
    investigation_id: int, payload: ActionCreate, user: CurrentUser, db: DbSession
) -> InvestigationAction:
    inv = _load(db, investigation_id)
    if not _can_edit(user, inv):
        raise Forbidden()
    action = InvestigationAction(
        investigation_id=inv.id,
        title=payload.title,
        owner_id=payload.owner_id or user.id,
        due_date=payload.due_date,
    )
    db.add(action)
    db.flush()
    db.refresh(action)
    return action

@router.patch(
    "/investigations/{investigation_id}/actions/{action_id}",
    response_model=ActionOut,
    dependencies=[_write],
)
def update_action(
    investigation_id: int, action_id: int, payload: ActionUpdate, user: CurrentUser, db: DbSession
) -> InvestigationAction:
    inv = _load(db, investigation_id)
    if not _can_edit(user, inv):
        raise Forbidden()
    action = next((a for a in inv.actions if a.id == action_id), None)
    if action is None:
        raise NotFound("Action", action_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(action, key, value)
    db.flush()
    db.refresh(action)
    return action

@router.delete(
    "/investigations/{investigation_id}/actions/{action_id}", status_code=204, dependencies=[_write]
)
def delete_action(investigation_id: int, action_id: int, user: CurrentUser, db: DbSession) -> None:
    inv = _load(db, investigation_id)
    if not _can_edit(user, inv):
        raise Forbidden()
    action = next((a for a in inv.actions if a.id == action_id), None)
    if action is None:
        raise NotFound("Action", action_id)
    db.delete(action)

@router.get("/stakeholders", response_model=list[StakeholderOut])
def list_stakeholders(_: CurrentUser, db: DbSession) -> list[Stakeholder]:
    return list(db.scalars(select(Stakeholder).order_by(Stakeholder.name)))

@router.put(
    "/investigations/{investigation_id}/stakeholders",
    response_model=InvestigationOut,
    dependencies=[_write],
)
def set_stakeholders(
    investigation_id: int, payload: list[StakeholderAssignment], user: CurrentUser, db: DbSession
) -> InvestigationOut:
    inv = _load(db, investigation_id)
    if not _can_edit(user, inv):
        raise Forbidden()
    ids = {s.stakeholder_id for s in payload}
    found = set(db.scalars(select(Stakeholder.id).where(Stakeholder.id.in_(ids)))) if ids else set()
    missing = ids - found
    if missing:
        raise NotFound("Stakeholder", ", ".join(map(str, sorted(missing))))
    inv.stakeholders = [
        InvestigationStakeholder(stakeholder_id=s.stakeholder_id, role=s.role, sort=i)
        for i, s in enumerate(payload)
    ]
    db.flush()
    db.expire(inv)
    return _to_out(db, _load(db, investigation_id))

class RootCauseRequest(BaseModel):
    metric_key: str
    filters: list[Filter] = Field(default_factory=list, max_length=8)
    period_start: date
    period_end: date
    baseline_start: date
    baseline_end: date

@router.post(
    "/root-cause",
    response_model=RootCauseAnalysis,
    dependencies=[Depends(require(Permission.run_analytics))],
)
def root_cause(payload: RootCauseRequest, _: CurrentUser, db: DbSession) -> RootCauseAnalysis:
    if payload.metric_key not in METRICS:
        raise BadRequest(f"Unknown metric '{payload.metric_key}'")
    if payload.period_start > payload.period_end or payload.baseline_start > payload.baseline_end:
        raise BadRequest("Window start must be on or before its end")
    return analyze(
        db,
        metric_key=payload.metric_key,
        filters=payload.filters,
        period_start=payload.period_start,
        period_end=payload.period_end,
        baseline_start=payload.baseline_start,
        baseline_end=payload.baseline_end,
    )

@router.get("/investigations/{investigation_id}/root-cause", response_model=RootCauseAnalysis)
def investigation_root_cause(investigation_id: int, _: CurrentUser, db: DbSession) -> RootCauseAnalysis:
    inv = _load(db, investigation_id)
    return analyze(
        db,
        metric_key=inv.metric_key,
        filters=[Filter.model_validate(f) for f in inv.filters or []],
        period_start=inv.period_start,
        period_end=inv.period_end,
        baseline_start=inv.baseline_start,
        baseline_end=inv.baseline_end,
    )
