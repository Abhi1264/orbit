from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from probelens.analytics.dimensions import Filter
from probelens.analytics.meta import get_meta
from probelens.analytics.metrics import METRICS, MetricFormat, format_value
from probelens.analytics.query import MetricQuery, run_metric_query
from probelens.api.deps import CurrentUser, DbSession, require
from probelens.core.errors import BadRequest, NotFound
from probelens.core.permissions import Permission
from probelens.models import Checklist, Decision, Experiment, Investigation, Release, ReleaseEvent, Sop, User
from probelens.models.enums import ChecklistStatus, InvestigationStatus, ReleaseStatus
from probelens.schemas.ops import (
    ChecklistOut,
    ChecklistProgress,
    EntityRef,
    ImpactMetric,
    ReleaseCreate,
    ReleaseImpact,
    ReleaseNoteCreate,
    ReleaseOut,
    ReleaseSummary,
    ReleaseUpdate,
)
from probelens.services.projects import default_project_id

router = APIRouter(prefix="/releases", tags=["releases"], dependencies=[Depends(require(Permission.view))])

_write = Depends(require(Permission.manage_releases))

# Metrics worth a before/after read for any release. Lagged metrics (returns,
# delivery) are excluded: a week after launch is too soon for them to mean anything.
IMPACT_METRICS = [
    "conversion",
    "checkout_conversion",
    "payment_success_rate",
    "add_to_cart_rate",
    "bounce_rate",
    "aov",
]
IMPACT_WINDOW_DAYS = 7

# Releases whose affected areas touch these keywords get an extra metric in the read.
AREA_METRICS = {
    "search": "search_to_product_view_rate",
    "discovery": "search_to_product_view_rate",
    "payments": "payment_failure_rate",
    "checkout": "payment_failure_rate",
}


def checklist_out(c: Checklist) -> ChecklistOut:
    items = list(c.items or [])
    return ChecklistOut(
        id=c.id,
        sop_id=c.sop_id,
        release_id=c.release_id,
        title=c.title,
        owner=c.owner,
        status=c.status,
        items=items,
        done_count=sum(1 for i in items if i.get("done")),
        total_count=len(items),
        updated_at=c.updated_at,
    )


def _load(db: Session, release_id: int) -> Release:
    rel = db.get(
        Release,
        release_id,
        options=[
            selectinload(Release.owner),
            selectinload(Release.timeline).selectinload(ReleaseEvent.actor),
        ],
    )
    if rel is None:
        raise NotFound("Release", release_id)
    return rel


def _checklists_for(db: Session, release_ids: list[int]) -> dict[int, list[Checklist]]:
    if not release_ids:
        return {}
    rows = db.scalars(
        select(Checklist)
        .options(selectinload(Checklist.owner))
        .where(Checklist.release_id.in_(release_ids))
        .order_by(Checklist.created_at)
    ).all()
    out: dict[int, list[Checklist]] = {}
    for c in rows:
        out.setdefault(c.release_id, []).append(c)  # type: ignore[arg-type]
    return out


def _open_investigations(db: Session, release_ids: list[int]) -> dict[int, int]:
    if not release_ids:
        return {}
    rows = db.execute(
        select(Investigation.release_id, func.count())
        .where(
            Investigation.release_id.in_(release_ids),
            Investigation.status.notin_([InvestigationStatus.resolved, InvestigationStatus.closed]),
        )
        .group_by(Investigation.release_id)
    ).all()
    return {rid: n for rid, n in rows}


def _summary(rel: Release, checklists: list[Checklist], open_inv: int) -> ReleaseSummary:
    progress = None
    if checklists:
        items = [i for c in checklists for i in (c.items or [])]
        progress = ChecklistProgress(done=sum(1 for i in items if i.get("done")), total=len(items))
    return ReleaseSummary(
        id=rel.id,
        version=rel.version,
        name=rel.name,
        platform=rel.platform,
        status=rel.status,
        release_date=rel.release_date,
        rollout_percent=rel.rollout_percent,
        owner=rel.owner,
        affected_areas=list(rel.affected_areas or []),
        experiment_id=rel.experiment_id,
        checklist_progress=progress,
        open_investigations=open_inv,
        updated_at=rel.updated_at,
    )


@router.get("", response_model=list[ReleaseSummary])
def list_releases(
    _: CurrentUser,
    db: DbSession,
    platform: str | None = Query(default=None),
    status: ReleaseStatus | None = Query(default=None),
) -> list[ReleaseSummary]:
    stmt = select(Release).options(selectinload(Release.owner)).order_by(Release.release_date.desc())
    if platform:
        stmt = stmt.where(Release.platform == platform)
    if status:
        stmt = stmt.where(Release.status == status)
    rels = db.scalars(stmt).all()
    ids = [r.id for r in rels]
    cls = _checklists_for(db, ids)
    inv = _open_investigations(db, ids)
    return [_summary(r, cls.get(r.id, []), inv.get(r.id, 0)) for r in rels]


def _to_out(db: Session, rel: Release) -> ReleaseOut:
    cls = _checklists_for(db, [rel.id]).get(rel.id, [])
    invs = db.scalars(
        select(Investigation)
        .where(Investigation.release_id == rel.id)
        .order_by(Investigation.updated_at.desc())
    ).all()
    decisions = db.scalars(select(Decision).where(Decision.release_id == rel.id)).all()
    exp = db.get(Experiment, rel.experiment_id) if rel.experiment_id else None
    base = _summary(
        rel,
        cls,
        sum(1 for i in invs if i.status not in (InvestigationStatus.resolved, InvestigationStatus.closed)),
    )
    return ReleaseOut(
        **base.model_dump(),
        description=rel.description,
        timeline=sorted(rel.timeline, key=lambda e: e.occurred_at),  # type: ignore[arg-type]
        checklists=[checklist_out(c) for c in cls],
        investigations=[
            EntityRef(type="investigation", id=i.id, title=i.title, status=i.status) for i in invs
        ],
        decisions=[EntityRef(type="decision", id=d.id, title=d.title, status=d.status) for d in decisions],
        experiment=EntityRef(type="experiment", id=exp.id, title=exp.name, status=exp.status)
        if exp
        else None,
        created_at=rel.created_at,
    )


@router.get("/{release_id}", response_model=ReleaseOut)
def get_release(release_id: int, _: CurrentUser, db: DbSession) -> ReleaseOut:
    return _to_out(db, _load(db, release_id))


def _event(rel: Release, user: User, kind: str, note: str) -> None:
    rel.timeline.append(ReleaseEvent(occurred_at=datetime.now(UTC), kind=kind, note=note, actor_id=user.id))


def _start_checklist(
    db: Session, rel: Release, sop_id: int, user: User, title: str | None = None
) -> Checklist:
    sop = db.get(Sop, sop_id)
    if sop is None:
        raise NotFound("SOP", sop_id)
    checklist = Checklist(
        sop_id=sop.id,
        release_id=rel.id,
        title=title or f"{rel.version} {rel.platform} — {sop.title}",
        owner_id=user.id,
        status=ChecklistStatus.not_started,
        items=[{**item, "done": False, "owner_id": None, "done_at": None} for item in (sop.items or [])],
    )
    db.add(checklist)
    return checklist


@router.post("", response_model=ReleaseOut, status_code=201, dependencies=[_write])
def create_release(payload: ReleaseCreate, user: CurrentUser, db: DbSession) -> ReleaseOut:
    dup = db.scalar(
        select(func.count()).where(Release.version == payload.version, Release.platform == payload.platform)
    )
    if dup:
        raise BadRequest(f"Release {payload.version} for {payload.platform} already exists")
    if payload.experiment_id is not None and db.get(Experiment, payload.experiment_id) is None:
        raise NotFound("Experiment", payload.experiment_id)
    rel = Release(
        project_id=default_project_id(db),
        version=payload.version.strip(),
        name=payload.name.strip(),
        description=payload.description.strip(),
        platform=payload.platform,
        owner_id=user.id,
        status=ReleaseStatus.planned,
        release_date=payload.release_date,
        rollout_percent=0,
        affected_areas=payload.affected_areas,
        experiment_id=payload.experiment_id,
    )
    _event(rel, user, "status_change", "Planned")
    db.add(rel)
    db.flush()
    if payload.sop_id:
        _start_checklist(db, rel, payload.sop_id, user)
        db.flush()
    return _to_out(db, _load(db, rel.id))


_STATUS_LABEL = {
    ReleaseStatus.planned: "Planned",
    ReleaseStatus.in_progress: "In progress",
    ReleaseStatus.rolling_out: "Rolling out",
    ReleaseStatus.completed: "Completed",
    ReleaseStatus.rolled_back: "Rolled back",
}


@router.patch("/{release_id}", response_model=ReleaseOut, dependencies=[_write])
def update_release(release_id: int, payload: ReleaseUpdate, user: CurrentUser, db: DbSession) -> ReleaseOut:
    rel = _load(db, release_id)
    data = payload.model_dump(exclude_unset=True)
    note = data.pop("note", None)

    if "status" in data and data["status"] != rel.status:
        new = data["status"]
        text = _STATUS_LABEL[new]
        if new == ReleaseStatus.completed and "rollout_percent" not in data:
            data["rollout_percent"] = 100
        if new == ReleaseStatus.rolled_back and "rollout_percent" not in data:
            data["rollout_percent"] = 0
        _event(rel, user, "status_change", f"{text}{' — ' + note if note else ''}")
        note = None
    if "rollout_percent" in data and data["rollout_percent"] != rel.rollout_percent:
        pct = data["rollout_percent"]
        _event(rel, user, "rollout", f"Rollout {pct}%{' — ' + note if note else ''}")
        note = None
        if rel.status == ReleaseStatus.planned and pct > 0 and "status" not in data:
            data["status"] = ReleaseStatus.rolling_out
    if data.get("experiment_id") is not None and db.get(Experiment, data["experiment_id"]) is None:
        raise NotFound("Experiment", data["experiment_id"])
    for k, v in data.items():
        setattr(rel, k, v)
    if note:
        _event(rel, user, "note", note)
    db.flush()
    return _to_out(db, _load(db, rel.id))


@router.post("/{release_id}/events", response_model=ReleaseOut, status_code=201, dependencies=[_write])
def add_release_note(
    release_id: int, payload: ReleaseNoteCreate, user: CurrentUser, db: DbSession
) -> ReleaseOut:
    rel = _load(db, release_id)
    _event(rel, user, payload.kind, payload.note.strip())
    db.flush()
    return _to_out(db, _load(db, rel.id))


@router.post("/{release_id}/checklists", response_model=ReleaseOut, status_code=201, dependencies=[_write])
def run_sop_for_release(
    release_id: int, sop_id: int = Query(...), *, user: CurrentUser, db: DbSession
) -> ReleaseOut:
    rel = _load(db, release_id)
    _start_checklist(db, rel, sop_id, user)
    _event(rel, user, "note", "Launch checklist started")
    db.flush()
    return _to_out(db, _load(db, rel.id))


@router.delete("/{release_id}", status_code=204, dependencies=[_write])
def delete_release(release_id: int, _: CurrentUser, db: DbSession) -> None:
    rel = _load(db, release_id)
    if rel.status != ReleaseStatus.planned:
        raise BadRequest(
            "Only planned releases can be deleted; roll back or complete a shipped release instead"
        )
    db.delete(rel)


# --------------------------------------------------------------------------- impact


def _tone(m_key: str, rel_change: float | None) -> str:
    if rel_change is None:
        return "unknown"
    if abs(rel_change) < 0.01:
        return "neutral"
    good = (rel_change > 0) == METRICS[m_key].higher_is_better
    return "good" if good else "bad"


def _fmt_change(fmt: MetricFormat, before: float | None, after: float | None) -> str:
    if before is None or after is None:
        return "—"
    if fmt in (MetricFormat.percent, MetricFormat.ratio):
        pp = (after - before) * 100
        return f"{pp:+.2f} pp"
    if before == 0:
        return "—"
    return f"{(after - before) / before * 100:+.1f}%"


@router.get("/{release_id}/impact", response_model=ReleaseImpact)
def release_impact(release_id: int, _: CurrentUser, db: DbSession) -> ReleaseImpact:
    """Seven days after the release versus the seven days before, on the release's platform.

    This is a read, not a causal estimate: anything else that happened in the same
    week is mixed in. The experiment platform is the tool for causal answers; this view
    exists so a release owner sees the shape of the week immediately.
    """
    rel = _load(db, release_id)
    meta = get_meta()
    data_end = meta.data_end or date.today()
    after_start = rel.release_date
    after_end = min(after_start + timedelta(days=IMPACT_WINDOW_DAYS - 1), data_end)
    before_end = after_start - timedelta(days=1)
    before_start = before_end - timedelta(days=IMPACT_WINDOW_DAYS - 1)
    filters = (
        [] if rel.platform == "all" else [Filter(dimension="platform", operator="eq", value=rel.platform)]
    )
    scope = [] if rel.platform == "all" else [f"platform = {rel.platform}"]

    keys = list(IMPACT_METRICS)
    for area in rel.affected_areas or []:
        extra = AREA_METRICS.get(str(area).lower())
        if extra and extra not in keys:
            keys.append(extra)

    metrics: list[ImpactMetric] = []
    if after_end < after_start:
        note = "Release date is after the end of the data; no post-release window to read yet."
    else:
        days_after = (after_end - after_start).days + 1
        note = (
            f"{days_after} day(s) after launch vs the {IMPACT_WINDOW_DAYS} days before, "
            f"{'on ' + rel.platform if rel.platform != 'all' else 'store-wide'}. "
            "Observational read — other changes in the same week are mixed in."
        )
        for key in keys:
            m = METRICS[key]
            res = run_metric_query(
                MetricQuery(
                    metric=key,
                    date_from=after_start,
                    date_to=after_end,
                    filters=filters,
                    granularity=None,
                    compare_from=before_start,
                    compare_to=before_end,
                )
            )
            s = res.series[0] if res.series else None
            after = s.total.value if s else None
            before = s.compare_total.value if s and s.compare_total else None
            abs_change = (after - before) if after is not None and before is not None else None
            rel_change = (after - before) / before if after is not None and before not in (None, 0) else None
            metrics.append(
                ImpactMetric(
                    metric_key=key,
                    label=m.label,
                    format=m.format,
                    higher_is_better=m.higher_is_better,
                    before=before,
                    after=after,
                    abs_change=abs_change,
                    rel_change=rel_change,
                    formatted_before=format_value(m.format, before),
                    formatted_after=format_value(m.format, after),
                    formatted_change=_fmt_change(m.format, before, after),
                    tone=_tone(key, rel_change),  # type: ignore[arg-type]
                )
            )
    return ReleaseImpact(
        before_start=before_start,
        before_end=before_end,
        after_start=after_start,
        after_end=after_end,
        scope=scope,
        metrics=metrics,
        note=note,
    )
