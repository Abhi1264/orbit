from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from probelens.ai import planner
from probelens.ai.agent import ask, build_tool_context
from probelens.ai.provider import get_provider
from probelens.ai.schemas import (
    AiRunSummary,
    AnalystAnswer,
    AskRequest,
    AskResponse,
    PlannedQuery,
    PlanRequest,
    PlanResponse,
    Suggestion,
    ToolCallRecord,
)
from probelens.analytics.metrics import get_metric
from probelens.api.deps import CurrentUser, DbSession, require
from probelens.core.errors import NotFound
from probelens.core.permissions import Permission, has_permission
from probelens.models import AiRun

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(require(Permission.use_analyst))])

@router.post("/ask", response_model=AskResponse)
def ask_analyst(body: AskRequest, user: CurrentUser, db: DbSession) -> AskResponse:
    return ask(db, user, body.question.strip(), body.context, body.mode)

@router.post("/plan", response_model=PlanResponse)
def plan_query(body: PlanRequest, _: CurrentUser, db: DbSession) -> PlanResponse:
    """Natural language → explorer query. Deterministic; the LLM is not needed for this."""
    tctx = build_tool_context(db)
    plan = planner.parse(body.text, tctx.today, tctx.dimension_values)
    metric = plan.metric or body.context.metric or "conversion"
    filters = plan.filters or list(body.context.filters)
    d = plan.dates
    if not d.explicit and body.context.date_from and body.context.date_to:
        d.date_from, d.date_to = body.context.date_from, body.context.date_to
    # The explorer always shows a comparison; keep it aligned to the window.
    cmp_from, cmp_to = planner.previous_window(d.date_from, d.date_to)
    confidence = "high" if plan.metric and not plan.unresolved else "medium" if plan.metric else "low"
    return PlanResponse(
        query=PlannedQuery(
            metric=metric,
            date_from=d.date_from,
            date_to=d.date_to,
            filters=filters,
            breakdown=plan.breakdown,
            granularity=d.granularity,
            compare_from=cmp_from,
            compare_to=cmp_to,
        ),
        explanation=planner.describe(plan)
        if plan.metric
        else f"No metric recognised; defaulting to {metric}. " + planner.describe(plan),
        confidence=confidence,
        unresolved=plan.unresolved,
        mode="demo",
    )

@router.get("/runs", response_model=list[AiRunSummary])
def list_runs(
    user: CurrentUser, db: DbSession, limit: int = Query(default=20, ge=1, le=100)
) -> list[AiRunSummary]:
    stmt = select(AiRun).order_by(AiRun.created_at.desc()).limit(limit)
    if not has_permission(user.role, Permission.manage_users):
        stmt = stmt.where(AiRun.user_id == user.id)
    return [
        AiRunSummary(
            id=r.id,
            question=r.question,
            mode=r.mode,  # type: ignore[arg-type]
            model=r.model,
            summary=(r.response or {}).get("summary", ""),
            tool_count=len(r.tool_calls or []),
            latency_ms=r.latency_ms,
            error=r.error,
            created_at=r.created_at,
        )
        for r in db.scalars(stmt)
    ]

@router.get("/runs/{run_id}", response_model=AskResponse)
def get_run(run_id: int, user: CurrentUser, db: DbSession) -> AskResponse:
    r = db.get(AiRun, run_id)
    if r is None or (r.user_id != user.id and not has_permission(user.role, Permission.manage_users)):
        raise NotFound("Run not found")
    return AskResponse(
        run_id=r.id,
        mode=r.mode,  # type: ignore[arg-type]
        model=r.model,
        question=r.question,
        answer=AnalystAnswer.model_validate(r.response),
        tool_calls=[ToolCallRecord.model_validate(c) for c in r.tool_calls or []],
        latency_ms=r.latency_ms,
        created_at=r.created_at,
    )

@router.get("/status")
def analyst_status(_: CurrentUser) -> dict[str, str | bool]:
    p = get_provider()
    return {
        "llm_enabled": p is not None,
        "model": p.model if p else "playbook",
        "mode": "llm" if p else "demo",
    }

@router.get("/suggestions", response_model=list[Suggestion])
def suggestions(
    _: CurrentUser,
    metric: str | None = None,
    experiment_id: int | None = None,
    investigation_id: int | None = None,
) -> list[Suggestion]:
    out: list[Suggestion] = [
        Suggestion(text="Why did conversion fall last week?", kind="why"),
        Suggestion(text="What needs attention right now?", kind="attention"),
        Suggestion(text="Payment success rate on Android over the last 30 days", kind="what"),
        Suggestion(text="Show the checkout funnel by platform", kind="funnel"),
        Suggestion(text="How is the new product page CTA experiment doing?", kind="experiment"),
        Suggestion(text="Conversion by traffic source last 14 days", kind="what"),
    ]
    if metric:
        label = get_metric(metric).label.lower()
        out = [
            Suggestion(text=f"Why did {label} change in this period?", kind="why"),
            Suggestion(text=f"{label.capitalize()} by platform in this period", kind="what"),
            Suggestion(text=f"{label.capitalize()} by traffic source in this period", kind="what"),
            *out[1:3],
        ]
    if experiment_id:
        out = [Suggestion(text="Should we ship this experiment?", kind="experiment"), *out[:3]]
    if investigation_id:
        out = [
            Suggestion(text="Why did this metric change in the investigation period?", kind="why"),
            *out[1:4],
        ]
    return out
