from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from probelens.api.deps import CurrentUser, DbSession, require
from probelens.core.errors import NotFound
from probelens.core.permissions import Permission
from probelens.models import Decision, Experiment, Investigation, Release
from probelens.models.enums import DecisionStatus
from probelens.schemas.ops import DecisionCreate, DecisionOut, DecisionSummary, DecisionUpdate, EntityRef
from probelens.services.projects import default_project_id

router = APIRouter(prefix="/decisions", tags=["decisions"], dependencies=[Depends(require(Permission.view))])

_write = Depends(require(Permission.manage_decisions))


def _links(db: Session, d: Decision) -> list[EntityRef]:
    out: list[EntityRef] = []
    if d.investigation_id and (inv := db.get(Investigation, d.investigation_id)):
        out.append(EntityRef(type="investigation", id=inv.id, title=inv.title, status=inv.status))
    if d.experiment_id and (exp := db.get(Experiment, d.experiment_id)):
        out.append(EntityRef(type="experiment", id=exp.id, title=exp.name, status=exp.status))
    if d.release_id and (rel := db.get(Release, d.release_id)):
        out.append(
            EntityRef(type="release", id=rel.id, title=f"{rel.version} · {rel.name}", status=rel.status)
        )
    return out


def _due(d: Decision, today: date) -> bool:
    return d.status == DecisionStatus.decided and d.follow_up_date is not None and d.follow_up_date <= today


def _summary(db: Session, d: Decision, today: date) -> DecisionSummary:
    return DecisionSummary(
        id=d.id,
        title=d.title,
        status=d.status,
        owner=d.owner,
        decided_on=d.decided_on,
        follow_up_date=d.follow_up_date,
        follow_up_due=_due(d, today),
        linked=_links(db, d),
        decision=d.decision,
        updated_at=d.updated_at,
    )


def _out(db: Session, d: Decision, today: date) -> DecisionOut:
    return DecisionOut(
        **_summary(db, d, today).model_dump(),
        context=d.context,
        evidence=d.evidence,
        alternatives=d.alternatives,
        expected_impact=d.expected_impact,
        investigation_id=d.investigation_id,
        experiment_id=d.experiment_id,
        release_id=d.release_id,
        created_at=d.created_at,
    )


def _load(db: Session, decision_id: int) -> Decision:
    d = db.get(Decision, decision_id, options=[selectinload(Decision.owner)])
    if d is None:
        raise NotFound("Decision", decision_id)
    return d


def _validate_links(db: Session, data: dict) -> None:
    for key, model, label in (
        ("investigation_id", Investigation, "Investigation"),
        ("experiment_id", Experiment, "Experiment"),
        ("release_id", Release, "Release"),
    ):
        if data.get(key) is not None and db.get(model, data[key]) is None:
            raise NotFound(label, data[key])


@router.get("", response_model=list[DecisionSummary])
def list_decisions(
    _: CurrentUser,
    db: DbSession,
    status: DecisionStatus | None = Query(default=None),
    experiment_id: int | None = Query(default=None),
    investigation_id: int | None = Query(default=None),
    release_id: int | None = Query(default=None),
    due_only: bool = Query(default=False),
) -> list[DecisionSummary]:
    stmt = (
        select(Decision)
        .options(selectinload(Decision.owner))
        .order_by(Decision.decided_on.desc(), Decision.id.desc())
    )
    if status:
        stmt = stmt.where(Decision.status == status)
    if experiment_id:
        stmt = stmt.where(Decision.experiment_id == experiment_id)
    if investigation_id:
        stmt = stmt.where(Decision.investigation_id == investigation_id)
    if release_id:
        stmt = stmt.where(Decision.release_id == release_id)
    today = date.today()
    rows = [_summary(db, d, today) for d in db.scalars(stmt).all()]
    return [r for r in rows if r.follow_up_due] if due_only else rows


@router.get("/{decision_id}", response_model=DecisionOut)
def get_decision(decision_id: int, _: CurrentUser, db: DbSession) -> DecisionOut:
    return _out(db, _load(db, decision_id), date.today())


@router.post("", response_model=DecisionOut, status_code=201, dependencies=[_write])
def create_decision(payload: DecisionCreate, user: CurrentUser, db: DbSession) -> DecisionOut:
    data = payload.model_dump()
    _validate_links(db, data)
    d = Decision(
        project_id=default_project_id(db),
        owner_id=user.id,
        **{**data, "decided_on": data["decided_on"] or date.today()},
    )
    db.add(d)
    db.flush()
    return _out(db, _load(db, d.id), date.today())


@router.patch("/{decision_id}", response_model=DecisionOut, dependencies=[_write])
def update_decision(decision_id: int, payload: DecisionUpdate, _: CurrentUser, db: DbSession) -> DecisionOut:
    d = _load(db, decision_id)
    data = payload.model_dump(exclude_unset=True)
    _validate_links(db, data)
    for k, v in data.items():
        setattr(d, k, v)
    db.flush()
    return _out(db, d, date.today())


@router.delete("/{decision_id}", status_code=204, dependencies=[_write])
def delete_decision(decision_id: int, _: CurrentUser, db: DbSession) -> None:
    db.delete(_load(db, decision_id))
