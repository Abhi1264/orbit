import re
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from probelens.analytics.dimensions import Filter
from probelens.analytics.meta import get_meta
from probelens.analytics.metrics import METRICS
from probelens.api.deps import CurrentUser, DbSession, require
from probelens.core.errors import BadRequest, Forbidden, NotFound
from probelens.core.permissions import Permission
from probelens.experiments.analysis import ExperimentResults, ExperimentSpec, analyze
from probelens.experiments.assignment import VariantSpec
from probelens.experiments.memo import build_memo
from probelens.models import Decision, Experiment, ExperimentVariant
from probelens.models.enums import DecisionStatus, ExperimentDecision, ExperimentStatus, Role
from probelens.schemas.experiments import (
    DecisionIn,
    ExperimentCreate,
    ExperimentOut,
    ExperimentSummary,
    ExperimentUpdate,
    MemoOut,
    VariantIn,
)
from probelens.services.projects import default_project_id

router = APIRouter(tags=["experiments"], dependencies=[Depends(require(Permission.view))])

_manage = Depends(require(Permission.manage_experiments))
_decide = Depends(require(Permission.decide_experiments))

_LOAD = [
    selectinload(Experiment.owner),
    selectinload(Experiment.variants),
    selectinload(Experiment.decided_by),
]

def _load(db: Session, experiment_id: int) -> Experiment:
    exp = db.get(Experiment, experiment_id, options=_LOAD)
    if exp is None:
        raise NotFound("Experiment", experiment_id)
    return exp

def _can_edit(user, exp: Experiment) -> bool:
    return user.role in (Role.admin, Role.pm) or user.id == exp.owner_id

def _summary(exp: Experiment) -> dict:
    return {
        "id": exp.id,
        "key": exp.key,
        "name": exp.name,
        "status": exp.status,
        "owner": exp.owner,
        "start_date": exp.start_date,
        "end_date": exp.end_date,
        "primary_metric": exp.primary_metric,
        "primary_metric_label": METRICS[exp.primary_metric].label
        if exp.primary_metric in METRICS
        else exp.primary_metric,
        "guardrail_metrics": list(exp.guardrail_metrics or []),
        "traffic_percent": exp.traffic_percent,
        "variant_count": len(exp.variants),
        "decision": exp.decision,
        "has_exposure_events": exp.has_exposure_events,
        "updated_at": exp.updated_at,
    }

def _to_out(exp: Experiment) -> ExperimentOut:
    filters = [Filter.model_validate(f) for f in exp.audience_filters or []]
    return ExperimentOut(
        **_summary(exp),
        hypothesis=exp.hypothesis,
        description=exp.description,
        audience_filters=filters,
        filter_labels=[f.describe() for f in filters],
        min_sample_per_variant=exp.min_sample_per_variant,
        min_relative_effect=exp.min_relative_effect,
        min_duration_days=exp.min_duration_days,
        variants=exp.variants,
        decision_reason=exp.decision_reason,
        decided_at=exp.decided_at,
        decided_by=exp.decided_by,
        created_at=exp.created_at,
    )

def _spec(exp: Experiment) -> ExperimentSpec:
    control = next((v.key for v in exp.variants if v.is_control), exp.variants[0].key)
    return ExperimentSpec(
        key=exp.key,
        variants=[VariantSpec(v.key, v.weight) for v in exp.variants],
        control_key=control,
        start=exp.start_date,
        end=exp.end_date,
        primary_metric=exp.primary_metric,
        guardrail_metrics=list(exp.guardrail_metrics or []),
        audience_filters=[Filter.model_validate(f) for f in exp.audience_filters or []],
        traffic_percent=exp.traffic_percent,
        has_exposure_events=exp.has_exposure_events,
        min_sample_per_variant=exp.min_sample_per_variant,
        min_relative_effect=exp.min_relative_effect,
        min_duration_days=exp.min_duration_days,
    )

def _check_metrics(primary: str, guardrails: list[str]) -> None:
    for key in [primary, *guardrails]:
        if key not in METRICS:
            raise BadRequest(f"Unknown metric '{key}'")

def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s[:60] or "experiment"

def _apply_variants(exp: Experiment, variants: list[VariantIn]) -> None:
    exp.variants = [
        ExperimentVariant(
            key=v.key, name=v.name, description=v.description, weight=v.weight, is_control=v.is_control
        )
        for v in variants
    ]

def _as_of(db_as_of: date | None) -> date:
    return db_as_of or get_meta().data_end or date.today()

@router.get("/experiments", response_model=list[ExperimentSummary])
def list_experiments(db: DbSession, status: ExperimentStatus | None = None) -> list[ExperimentSummary]:
    stmt = select(Experiment).options(*_LOAD).order_by(Experiment.start_date.desc(), Experiment.id.desc())
    if status is not None:
        stmt = stmt.where(Experiment.status == status)
    return [ExperimentSummary(**_summary(e)) for e in db.scalars(stmt)]

@router.post("/experiments", response_model=ExperimentOut, status_code=201, dependencies=[_manage])
def create_experiment(payload: ExperimentCreate, user: CurrentUser, db: DbSession) -> ExperimentOut:
    _check_metrics(payload.primary_metric, payload.guardrail_metrics)
    key = payload.key or _slug(payload.name)
    if db.scalar(select(Experiment.id).where(Experiment.key == key)) is not None:
        raise BadRequest(f"An experiment with key '{key}' already exists")
    exp = Experiment(
        project_id=default_project_id(db),
        key=key,
        name=payload.name,
        hypothesis=payload.hypothesis,
        description=payload.description,
        owner_id=user.id,
        status=ExperimentStatus.draft,
        start_date=payload.start_date or date.today(),
        end_date=payload.end_date,
        primary_metric=payload.primary_metric,
        guardrail_metrics=payload.guardrail_metrics,
        audience_filters=[f.model_dump(exclude_none=True) for f in payload.audience_filters],
        traffic_percent=payload.traffic_percent,
        min_sample_per_variant=payload.min_sample_per_variant,
        min_relative_effect=payload.min_relative_effect,
        min_duration_days=payload.min_duration_days,
        has_exposure_events=False,
    )
    _apply_variants(exp, payload.variants)
    db.add(exp)
    db.flush()
    return _to_out(_load(db, exp.id))

@router.get("/experiments/{experiment_id}", response_model=ExperimentOut)
def get_experiment(experiment_id: int, db: DbSession) -> ExperimentOut:
    return _to_out(_load(db, experiment_id))

_TRANSITIONS: dict[ExperimentStatus, set[ExperimentStatus]] = {
    ExperimentStatus.draft: {ExperimentStatus.running},
    ExperimentStatus.running: {ExperimentStatus.completed, ExperimentStatus.stopped},
    ExperimentStatus.completed: set(),
    ExperimentStatus.stopped: set(),
}

# Once an experiment has started, its design is frozen; only bookkeeping may change.
_DESIGN_FIELDS = {
    "primary_metric",
    "guardrail_metrics",
    "audience_filters",
    "traffic_percent",
    "variants",
    "start_date",
}

@router.patch("/experiments/{experiment_id}", response_model=ExperimentOut, dependencies=[_manage])
def update_experiment(
    experiment_id: int, payload: ExperimentUpdate, user: CurrentUser, db: DbSession
) -> ExperimentOut:
    exp = _load(db, experiment_id)
    if not _can_edit(user, exp):
        raise Forbidden()
    changes = payload.model_dump(exclude_unset=True)
    if exp.status != ExperimentStatus.draft and _DESIGN_FIELDS & set(changes):
        raise BadRequest(
            "The design of a started experiment cannot be changed; create a new experiment instead"
        )
    if "primary_metric" in changes or "guardrail_metrics" in changes:
        _check_metrics(
            changes.get("primary_metric", exp.primary_metric),
            changes.get("guardrail_metrics", list(exp.guardrail_metrics or [])),
        )
    if "variants" in changes:
        variants = payload.variants or []
        if len({v.key for v in variants}) != len(variants) or sum(v.is_control for v in variants) != 1:
            raise BadRequest("Variants need unique keys and exactly one control")
        _apply_variants(exp, variants)
        changes.pop("variants")
    if "audience_filters" in changes:
        changes["audience_filters"] = [
            f.model_dump(exclude_none=True) for f in payload.audience_filters or []
        ]
    new_status = changes.pop("status", None)
    for key, value in changes.items():
        setattr(exp, key, value)
    if new_status is not None and new_status != exp.status:
        if new_status not in _TRANSITIONS[exp.status]:
            raise BadRequest(f"Cannot move an experiment from {exp.status.value} to {new_status.value}")
        exp.status = new_status
        today = _as_of(None)
        if new_status == ExperimentStatus.running and exp.start_date is None:
            exp.start_date = today
        if new_status in (ExperimentStatus.completed, ExperimentStatus.stopped) and exp.end_date is None:
            exp.end_date = today
    if exp.end_date and exp.end_date < exp.start_date:
        raise BadRequest("End date must be on or after the start date")
    db.flush()
    db.expire(exp)
    return _to_out(_load(db, experiment_id))

@router.delete("/experiments/{experiment_id}", status_code=204, dependencies=[_manage])
def delete_experiment(experiment_id: int, user: CurrentUser, db: DbSession) -> None:
    exp = _load(db, experiment_id)
    if not _can_edit(user, exp):
        raise Forbidden()
    if exp.status != ExperimentStatus.draft:
        raise BadRequest("Only draft experiments can be deleted; stop a running experiment instead")
    db.delete(exp)
    db.flush()

@router.get("/experiments/{experiment_id}/results", response_model=ExperimentResults)
def experiment_results(
    experiment_id: int, db: DbSession, as_of: date | None = Query(default=None)
) -> ExperimentResults:
    exp = _load(db, experiment_id)
    return analyze(_spec(exp), _as_of(as_of))

@router.get("/experiments/{experiment_id}/memo", response_model=MemoOut)
def experiment_memo(experiment_id: int, db: DbSession, as_of: date | None = Query(default=None)) -> MemoOut:
    exp = _load(db, experiment_id)
    day = _as_of(as_of)
    results = analyze(_spec(exp), day)
    markdown = build_memo(
        name=exp.name,
        hypothesis=exp.hypothesis,
        owner=exp.owner.name,
        status=exp.status.value,
        results=results,
        recorded_decision=exp.decision.value if exp.decision else None,
        recorded_reason=exp.decision_reason,
    )
    return MemoOut(markdown=markdown, as_of=day)

@router.post("/experiments/{experiment_id}/decision", response_model=ExperimentOut, dependencies=[_decide])
def record_decision(
    experiment_id: int, payload: DecisionIn, user: CurrentUser, db: DbSession
) -> ExperimentOut:
    exp = _load(db, experiment_id)
    if exp.status == ExperimentStatus.draft:
        raise BadRequest("Start the experiment before recording a decision")
    now = datetime.now(UTC)
    exp.decision = payload.decision
    exp.decision_reason = payload.reason
    exp.decided_at = now
    exp.decided_by_id = user.id
    today = _as_of(None)
    if payload.decision != ExperimentDecision.continue_ and exp.status == ExperimentStatus.running:
        exp.status = (
            ExperimentStatus.stopped
            if payload.decision == ExperimentDecision.stop
            else ExperimentStatus.completed
        )
        exp.end_date = exp.end_date or today
    if payload.log:
        results = analyze(_spec(exp), today)
        primary = results.metrics[0]
        cmp = primary.comparisons[0] if primary.comparisons else None
        evidence = results.recommendation.headline
        if cmp is not None:
            evidence += (
                f". {primary.label}: {cmp.rel_diff * 100:+.1f}% "
                f"(95% CI {cmp.rel_ci_low * 100:+.1f}% to "
                f"{cmp.rel_ci_high * 100:+.1f}%, p = {cmp.p_value:.3g})"
                if cmp.rel_diff is not None and cmp.rel_ci_low is not None and cmp.rel_ci_high is not None
                else ""
            )
        db.add(
            Decision(
                project_id=exp.project_id,
                title=f"{exp.name}: {payload.decision.value}",
                context=exp.hypothesis,
                evidence=evidence,
                alternatives="",
                decision=payload.reason,
                expected_impact="",
                owner_id=user.id,
                status=DecisionStatus.decided,
                decided_on=today,
                experiment_id=exp.id,
            )
        )
    db.flush()
    db.expire(exp)
    return _to_out(_load(db, experiment_id))
