"""The analyst's tools. Every number the analyst states comes from one of these.

Tools are read-only wrappers over the same engines the UI uses (metric query,
funnel, root cause, experiment analysis, Postgres lookups). Arguments are
Pydantic models so the LLM's JSON is validated before anything runs, and each
tool returns both structured `data` (for the evidence drawer) and a compact
`summary` (what the model actually reads, to keep context small).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from probelens.ai import planner
from probelens.ai.schemas import ToolCallRecord
from probelens.analytics.dimensions import DIMENSIONS, Filter
from probelens.analytics.funnel import DEFAULT_FUNNEL, FUNNEL_EVENTS, FunnelQuery, FunnelSegment, run_funnel
from probelens.analytics.metrics import METRICS, format_value, get_metric
from probelens.analytics.query import MetricQuery, run_metric_query
from probelens.analytics.rootcause import analyze as root_cause_analyze
from probelens.experiments.analysis import ExperimentSpec
from probelens.experiments.analysis import analyze as experiment_analyze
from probelens.experiments.assignment import VariantSpec
from probelens.models import Anomaly, Decision, Experiment, Investigation, KnowledgeDocument, Release, Sop


@dataclass
class ToolContext:
    db: Session
    today: date  # latest day with data
    dimension_values: dict[str, list[str]]


class ToolResult(BaseModel):
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    run: Callable[[BaseModel, ToolContext], ToolResult]

    def openai_schema(self) -> dict[str, Any]:
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": schema},
        }


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v * 100:+.1f}%"


def _rel(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev is None or prev == 0:
        return None
    return (cur - prev) / prev


def _window(args: Any, ctx: ToolContext, default_days: int = 14) -> tuple[date, date]:
    """Resolve optional date_from/date_to; defaults to the last `default_days` days of data."""
    end = args.date_to or ctx.today
    start = args.date_from or (end - timedelta(days=default_days - 1))
    if start > end:
        raise ValueError("date_from must be on or before date_to")
    return start, end


# --------------------------------------------------------------------------- metric summary


class MetricSummaryArgs(BaseModel):
    metric: str = Field(description="Metric key, e.g. conversion, revenue, payment_success_rate")
    date_from: date | None = Field(
        default=None, description="Inclusive start; defaults to 14 days before date_to"
    )
    date_to: date | None = Field(
        default=None, description="Inclusive end; defaults to the latest day with data"
    )
    filters: list[Filter] = Field(default_factory=list, description="Scope, e.g. platform = android")
    compare_previous: bool = Field(default=True, description="Also compute the immediately preceding window")


def _metric_summary(a: MetricSummaryArgs, ctx: ToolContext) -> ToolResult:
    m = get_metric(a.metric)
    start, end = _window(a, ctx)
    cmp_from = cmp_to = None
    if a.compare_previous:
        cmp_from, cmp_to = planner.previous_window(start, end)
    res = run_metric_query(
        MetricQuery(
            metric=m.key,
            date_from=start,
            date_to=end,
            filters=a.filters,
            granularity="day",
            compare_from=cmp_from,
            compare_to=cmp_to,
        )
    )
    s = res.series[0]
    cur, prev = s.total.value, s.compare_total.value if s.compare_total else None
    rel = _rel(cur, prev)
    scope = ", ".join(f.describe() for f in a.filters) or "store-wide"
    summary = f"{m.label} ({scope}) {start:%-d %b}–{end:%-d %b}: {format_value(m.format, cur)}"
    if prev is not None:
        summary += (
            f" vs {format_value(m.format, prev)} in the previous {(end - start).days + 1} days ({_pct(rel)})"
        )
    if m.format.value == "percent" and cur is not None and prev is not None:
        summary += f", {(cur - prev) * 100:+.2f} pp"
    daily = [(p.bucket, p.value) for p in s.points]
    worst = min((p for p in s.points if p.value is not None), key=lambda p: p.value or 0, default=None)
    best = max((p for p in s.points if p.value is not None), key=lambda p: p.value or 0, default=None)
    return ToolResult(
        summary=summary,
        data={
            "metric": m.key,
            "label": m.label,
            "format": m.format.value,
            "higher_is_better": m.higher_is_better,
            "scope": scope,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "value": cur,
            "numerator": s.total.numerator,
            "denominator": s.total.denominator,
            "previous": prev,
            "rel_change": rel,
            "abs_change": (cur - prev) if cur is not None and prev is not None else None,
            "daily": daily,
            "min_day": {"bucket": worst.bucket, "value": worst.value} if worst else None,
            "max_day": {"bucket": best.bucket, "value": best.value} if best else None,
        },
    )


# --------------------------------------------------------------------------- breakdown


class BreakdownArgs(BaseModel):
    metric: str
    dimension: str = Field(description="Dimension key, e.g. platform, traffic_source, payment_method")
    date_from: date | None = None
    date_to: date | None = None
    filters: list[Filter] = Field(default_factory=list)
    compare_previous: bool = True
    limit: int = Field(default=8, ge=2, le=20)


def _breakdown(a: BreakdownArgs, ctx: ToolContext) -> ToolResult:
    m = get_metric(a.metric)
    if a.dimension not in DIMENSIONS:
        raise ValueError(f"Unknown dimension '{a.dimension}'")
    start, end = _window(a, ctx)
    cmp_from = cmp_to = None
    if a.compare_previous:
        cmp_from, cmp_to = planner.previous_window(start, end)
    res = run_metric_query(
        MetricQuery(
            metric=m.key,
            date_from=start,
            date_to=end,
            filters=a.filters,
            breakdown=a.dimension,
            granularity=None,
            compare_from=cmp_from,
            compare_to=cmp_to,
            limit=a.limit,
        )
    )
    total_den = sum((s.total.denominator or s.total.numerator or 0) for s in res.series) or 1
    rows = []
    for s in res.series:
        prev = s.compare_total.value if s.compare_total else None
        rows.append(
            {
                "segment": s.label,
                "key": s.key,
                "value": s.total.value,
                "previous": prev,
                "rel_change": _rel(s.total.value, prev),
                "abs_change": (s.total.value - prev)
                if s.total.value is not None and prev is not None
                else None,
                "share": (s.total.denominator or s.total.numerator or 0) / total_den,
                "numerator": s.total.numerator,
                "denominator": s.total.denominator,
            }
        )
    rows.sort(key=lambda r: -(r["share"] or 0))
    parts = []
    for r in rows[:6]:
        piece = f"{r['segment']} {format_value(m.format, r['value'])}"
        if r["previous"] is not None:
            piece += f" ({_pct(r['rel_change'])})"
        piece += f" [{r['share'] * 100:.0f}% of volume]"
        parts.append(piece)
    summary = (
        f"{m.label} by {DIMENSIONS[a.dimension].label.lower()} {start:%-d %b}–{end:%-d %b}: "
        + "; ".join(parts)
    )
    return ToolResult(
        summary=summary,
        data={
            "metric": m.key,
            "label": m.label,
            "format": m.format.value,
            "higher_is_better": m.higher_is_better,
            "dimension": a.dimension,
            "dimension_label": DIMENSIONS[a.dimension].label,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "rows": rows,
        },
    )


# --------------------------------------------------------------------------- funnel


class FunnelArgs(BaseModel):
    steps: list[str] = Field(
        default_factory=lambda: list(DEFAULT_FUNNEL),
        description=f"Ordered event names from: {', '.join(FUNNEL_EVENTS)}",
    )
    date_from: date | None = None
    date_to: date | None = None
    filters: list[Filter] = Field(default_factory=list)
    breakdown: str | None = Field(
        default=None, description="Session-level dimension to compare, e.g. platform"
    )


def _funnel(a: FunnelArgs, ctx: ToolContext) -> ToolResult:
    start, end = _window(a, ctx)
    res = run_funnel(
        FunnelQuery(
            steps=a.steps,
            date_from=start,
            date_to=end,
            segments=[FunnelSegment(label="Scope", filters=a.filters)],
            breakdown=a.breakdown,
            limit=6,
        )
    )
    series_out = []
    lines = []
    for s in res.series:
        steps = [
            {
                "event": st.event,
                "label": st.label,
                "sessions": st.sessions,
                "step_conversion": st.step_conversion,
                "overall_conversion": st.overall_conversion,
                "drop_off": st.drop_off,
            }
            for st in s.steps
        ]
        # Biggest leak: the transition with the lowest step conversion after the first step.
        leak = min(
            (st for st in s.steps[1:] if st.step_conversion is not None),
            key=lambda st: st.step_conversion or 1,
            default=None,
        )
        series_out.append(
            {
                "label": s.label,
                "total_sessions": s.total_sessions,
                "steps": steps,
                "biggest_leak": leak.label if leak else None,
            }
        )
        end_conv = s.steps[-1].overall_conversion if s.steps else None
        lines.append(
            f"{s.label}: {s.total_sessions:,} sessions, {_fmt_pct(end_conv)} reach "
            f"{s.steps[-1].label if s.steps else '?'}"
            + (
                f"; biggest leak before {leak.label} ({_fmt_pct(leak.step_conversion)} step conversion)"
                if leak
                else ""
            )
        )
    return ToolResult(
        summary=f"Funnel {' → '.join(FUNNEL_EVENTS.get(x, x) for x in a.steps)} {start:%-d %b}–{end:%-d %b}. "
        + " | ".join(lines),
        data={
            "steps": a.steps,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "series": series_out,
        },
    )


def _fmt_pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


# --------------------------------------------------------------------------- root cause


class RootCauseArgs(BaseModel):
    metric: str
    period_from: date = Field(description="Start of the window that looks wrong")
    period_to: date
    baseline_from: date | None = Field(default=None, description="Defaults to the 28 days before the period")
    baseline_to: date | None = None
    filters: list[Filter] = Field(default_factory=list)


def _root_cause(a: RootCauseArgs, ctx: ToolContext) -> ToolResult:
    b_to = a.baseline_to or (a.period_from - timedelta(days=1))
    b_from = a.baseline_from or (b_to - timedelta(days=27))
    rc = root_cause_analyze(
        ctx.db,
        metric_key=a.metric,
        filters=a.filters,
        period_start=a.period_from,
        period_end=a.period_to,
        baseline_start=b_from,
        baseline_end=b_to,
    )
    m = get_metric(a.metric)
    cands = [
        {
            "rank": c.rank,
            "kind": c.kind,
            "title": c.title,
            "summary": c.summary,
            "confidence": c.confidence,
            "explained": c.explained,
            "dimension": c.dimension,
            "key": c.key,
            "filters": [f.model_dump(exclude_none=True) for f in c.filters],
            "release_id": c.release_id,
            "experiment_id": c.experiment_id,
        }
        for c in rc.candidates[:6]
    ]
    head = (
        f"{m.label} {format_value(m.format, rc.overall.baseline)} → "
        f"{format_value(m.format, rc.overall.period)} "
        f"({_pct(rc.overall.rel_change)})."
    )
    top = "; ".join(f"#{c['rank']} {c['title']} [{c['confidence']}]" for c in cands[:4]) or "no candidates"
    return ToolResult(
        summary=(
            f"{head} Candidates: {top}. Releases in window: {len(rc.releases)}; "
            f"experiments: {len(rc.experiments)}."
        ),
        data={
            "metric": m.key,
            "label": m.label,
            "format": m.format.value,
            "overall": rc.overall.model_dump(mode="json"),
            "period": rc.period,
            "baseline": rc.baseline,
            "candidates": cands,
            "releases": [r.model_dump(mode="json") for r in rc.releases],
            "experiments": [e.model_dump(mode="json") for e in rc.experiments],
            "notes": rc.notes,
        },
    )


# --------------------------------------------------------------------------- anomalies


class AnomaliesArgs(BaseModel):
    status: Literal["open", "acknowledged", "investigating", "resolved", "all"] = "open"
    metric: str | None = None
    limit: int = Field(default=10, ge=1, le=30)


def _anomalies(a: AnomaliesArgs, ctx: ToolContext) -> ToolResult:
    stmt = select(Anomaly).order_by(Anomaly.period_end.desc(), Anomaly.zscore.desc())
    if a.status != "all":
        stmt = stmt.where(Anomaly.status == a.status)
    if a.metric:
        stmt = stmt.where(Anomaly.metric_key == a.metric)
    rows = list(ctx.db.scalars(stmt.limit(a.limit)))
    sev = {"high": 0, "medium": 1, "low": 2}
    rows.sort(key=lambda x: (sev.get(x.severity, 3), -abs(x.zscore)))
    out = []
    for x in rows:
        m = get_metric(x.metric_key)
        filters = [Filter.model_validate(f) for f in x.filters]
        scope = ", ".join(f.describe() for f in filters) or "store-wide"
        out.append(
            {
                "id": x.id,
                "metric": x.metric_key,
                "label": m.label,
                "scope": scope,
                "filters": [f.model_dump(exclude_none=True) for f in filters],
                "period_start": x.period_start.isoformat(),
                "period_end": x.period_end.isoformat(),
                "ongoing": x.period_end >= ctx.today,
                "expected": x.expected,
                "actual": x.actual,
                "direction": x.direction,
                "severity": x.severity,
                "zscore": x.zscore,
                "status": x.status,
                "investigation_id": x.investigation_id,
                "text": f"{m.label} {'up' if x.direction == 'up' else 'down'} ({scope}): "
                f"{format_value(m.format, x.actual)} vs expected {format_value(m.format, x.expected)}, "
                f"z {x.zscore:+.1f}, "
                f"{x.period_start:%-d %b}–{x.period_end:%-d %b}, {x.severity}",
            }
        )
    summary = f"{len(out)} {a.status} anomalies. " + " | ".join(o["text"] for o in out[:5])
    return ToolResult(summary=summary, data={"anomalies": out})


# --------------------------------------------------------------------------- releases


class ReleasesArgs(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    platform: Literal["android", "ios", "web", "all"] | None = None


def _releases(a: ReleasesArgs, ctx: ToolContext) -> ToolResult:
    end = a.date_to or ctx.today
    start = a.date_from or (end - timedelta(days=30))
    stmt = (
        select(Release)
        .where(Release.release_date.between(start, end))
        .order_by(Release.release_date.desc())
        .options(selectinload(Release.owner))
    )
    if a.platform:
        stmt = stmt.where(or_(Release.platform == a.platform, Release.platform == "all"))
    rows = list(ctx.db.scalars(stmt))
    out = [
        {
            "id": r.id,
            "version": r.version,
            "name": r.name,
            "platform": r.platform,
            "release_date": r.release_date.isoformat(),
            "status": r.status.value,
            "rollout_percent": r.rollout_percent,
            "affected_areas": list(r.affected_areas or []),
            "owner": r.owner.name,
        }
        for r in rows
    ]
    summary = f"{len(out)} releases {start:%-d %b}–{end:%-d %b}: " + "; ".join(
        f"{o['platform']} {o['version']} on {o['release_date'][5:]} ({o['status']}; "
        f"{', '.join(o['affected_areas']) or 'no areas listed'})"
        for o in out[:6]
    )
    return ToolResult(summary=summary, data={"releases": out})


# --------------------------------------------------------------------------- experiments


class ExperimentsArgs(BaseModel):
    status: Literal["draft", "running", "completed", "stopped", "all"] = "all"
    query: str | None = Field(default=None, description="Substring of the key or name")


def _experiments(a: ExperimentsArgs, ctx: ToolContext) -> ToolResult:
    stmt = select(Experiment).options(selectinload(Experiment.variants), selectinload(Experiment.owner))
    if a.status != "all":
        stmt = stmt.where(Experiment.status == a.status)
    if a.query:
        q = f"%{a.query.lower().replace(' ', '%')}%"
        stmt = stmt.where(or_(func.lower(Experiment.key).like(q), func.lower(Experiment.name).like(q)))
    rows = list(ctx.db.scalars(stmt.order_by(Experiment.start_date.desc())))
    out = [
        {
            "id": e.id,
            "key": e.key,
            "name": e.name,
            "status": e.status.value,
            "start_date": e.start_date.isoformat(),
            "end_date": e.end_date.isoformat() if e.end_date else None,
            "primary_metric": e.primary_metric,
            "guardrail_metrics": list(e.guardrail_metrics or []),
            "decision": e.decision.value if e.decision else None,
            "owner": e.owner.name,
        }
        for e in rows
    ]
    summary = f"{len(out)} experiments: " + "; ".join(
        f"{o['name']} ({o['key']}, {o['status']}, primary {o['primary_metric']}"
        + (f", decided {o['decision']}" if o["decision"] else "")
        + ")"
        for o in out[:8]
    )
    return ToolResult(summary=summary, data={"experiments": out})


class ExperimentResultsArgs(BaseModel):
    experiment: str = Field(description="Experiment key or numeric id")


def _experiment_results(a: ExperimentResultsArgs, ctx: ToolContext) -> ToolResult:
    stmt = select(Experiment).options(selectinload(Experiment.variants))
    stmt = (
        stmt.where(Experiment.id == int(a.experiment))
        if a.experiment.isdigit()
        else stmt.where(Experiment.key == a.experiment)
    )
    exp = ctx.db.scalars(stmt).first()
    if exp is None:
        # Fuzzy: substring on key/name.
        q = f"%{a.experiment.lower().replace(' ', '%')}%"
        exp = ctx.db.scalars(
            select(Experiment)
            .options(selectinload(Experiment.variants))
            .where(or_(func.lower(Experiment.key).like(q), func.lower(Experiment.name).like(q)))
        ).first()
    if exp is None:
        raise ValueError(f"No experiment matches '{a.experiment}'")
    if exp.status == "draft":
        return ToolResult(
            summary=f"{exp.name} is a draft; no results yet.",
            data={"id": exp.id, "key": exp.key, "status": "draft"},
        )
    control = next((v.key for v in exp.variants if v.is_control), exp.variants[0].key)
    spec = ExperimentSpec(
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
    r = experiment_analyze(spec, ctx.today)
    metrics_out = []
    lines = []
    for m in r.metrics:
        fmt = METRICS[m.metric_key].format
        cmp = m.comparisons[0] if m.comparisons else None
        ctrl = next((v for v in m.variants if v.key == control), None)
        trt = next((v for v in m.variants if cmp and v.key == cmp.variant), None)
        metrics_out.append(
            {
                "metric": m.metric_key,
                "label": m.label,
                "format": fmt.value,
                "role": m.role,
                "control": ctrl.value if ctrl else None,
                "treatment": trt.value if trt else None,
                "rel_diff": cmp.rel_diff if cmp else None,
                "rel_ci": [cmp.rel_ci_low, cmp.rel_ci_high] if cmp else None,
                "p_value": cmp.p_value if cmp else None,
                "direction": cmp.direction if cmp else None,
            }
        )
        if cmp and ctrl and trt:
            lines.append(
                f"{m.label} ({m.role}): {format_value(fmt, trt.value)} vs {format_value(fmt, ctrl.value)} "
                f"({_pct(cmp.rel_diff)}, CI {_pct(cmp.rel_ci_low)} to {_pct(cmp.rel_ci_high)}, "
                f"p={cmp.p_value:.3g}, {cmp.direction})"
            )
    rec = r.recommendation
    summary = (
        f"{exp.name} ({exp.status.value}, {r.exposure.total_users:,} users, {r.exposure.days_running} days). "
        + " | ".join(lines)
        + f". Recommendation: {rec.decision} ({rec.confidence}) — {rec.headline}."
        + (f" Recorded decision: {exp.decision.value}." if exp.decision else "")
    )
    return ToolResult(
        summary=summary,
        data={
            "id": exp.id,
            "key": exp.key,
            "name": exp.name,
            "status": exp.status.value,
            "hypothesis": exp.hypothesis,
            "exposure": r.exposure.model_dump(mode="json"),
            "metrics": metrics_out,
            "power": r.power.model_dump(mode="json"),
            "recommendation": rec.model_dump(mode="json"),
            "recorded_decision": exp.decision.value if exp.decision else None,
            "decision_reason": exp.decision_reason,
            "notes": r.notes,
        },
    )


# --------------------------------------------------------------------------- investigations & knowledge


class InvestigationsArgs(BaseModel):
    status: Literal["open", "investigating", "validating", "resolved", "closed", "active", "all"] = "active"
    metric: str | None = None
    limit: int = Field(default=8, ge=1, le=20)


def _investigations(a: InvestigationsArgs, ctx: ToolContext) -> ToolResult:
    stmt = select(Investigation).options(
        selectinload(Investigation.owner), selectinload(Investigation.findings)
    )
    if a.status == "active":
        stmt = stmt.where(Investigation.status.in_(["open", "investigating", "validating"]))
    elif a.status != "all":
        stmt = stmt.where(Investigation.status == a.status)
    if a.metric:
        stmt = stmt.where(Investigation.metric_key == a.metric)
    rows = list(ctx.db.scalars(stmt.order_by(Investigation.updated_at.desc()).limit(a.limit)))
    out = []
    for i in rows:
        filters = [Filter.model_validate(f) for f in i.filters or []]
        hyps = [f for f in i.findings if f.kind.value == "hypothesis"]
        out.append(
            {
                "id": i.id,
                "title": i.title,
                "status": i.status.value,
                "metric": i.metric_key,
                "scope": ", ".join(f.describe() for f in filters) or "store-wide",
                "period_start": i.period_start.isoformat(),
                "period_end": i.period_end.isoformat(),
                "owner": i.owner.name,
                "hypotheses": [
                    {"title": h.title, "state": h.state.value if h.state else None} for h in hyps[:4]
                ],
                "observation": i.observation or "",
                "decision": i.decision or "",
            }
        )
    summary = f"{len(out)} investigations: " + "; ".join(
        f"#{o['id']} {o['title']} ({o['status']}; {len(o['hypotheses'])} hypotheses)" for o in out[:6]
    )
    return ToolResult(summary=summary, data={"investigations": out})


class SearchArgs(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    limit: int = Field(default=6, ge=1, le=15)


def _search_knowledge(a: SearchArgs, ctx: ToolContext) -> ToolResult:
    """Full-text search over SOPs, knowledge documents and the decision log.

    Tries an all-terms match first, then relaxes to any-term so a query like
    "payment failure" still finds the payments runbook.
    """
    sources = (
        (KnowledgeDocument, "knowledge", KnowledgeDocument.body),
        (Sop, "sop", Sop.description),
        (Decision, "decision", Decision.decision),
    )
    out: list[dict[str, Any]] = []
    for ts in (func.plainto_tsquery("english", a.query), func.to_tsquery("english", _or_terms(a.query))):
        for model, kind, body_col in sources:
            rank = func.ts_rank(model.search_vector, ts)
            stmt = (
                select(model, rank.label("rank"))
                .where(model.search_vector.op("@@")(ts))
                .order_by(rank.desc())
                .limit(a.limit)
            )
            for row, score in ctx.db.execute(stmt):
                body = getattr(row, body_col.key) or ""
                out.append(
                    {
                        "kind": kind,
                        "id": row.id,
                        "title": row.title,
                        "snippet": body[:280],
                        "rank": float(score),
                    }
                )
        if out:
            break
    out.sort(key=lambda r: -r["rank"])
    out = out[: a.limit]
    summary = f"{len(out)} documents for '{a.query}': " + "; ".join(
        f"[{o['kind']}] {o['title']}" for o in out
    )
    return ToolResult(summary=summary, data={"results": out})


def _or_terms(q: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", q.lower()) if len(w) > 2]
    return " | ".join(words) or "zzz"


# --------------------------------------------------------------------------- planner as a tool


class PlanArgs(BaseModel):
    text: str = Field(description="Natural-language description of a metric question")


def _plan(a: PlanArgs, ctx: ToolContext) -> ToolResult:
    p = planner.parse(a.text, ctx.today, ctx.dimension_values)
    return ToolResult(
        summary=planner.describe(p) + (f" (unresolved: {', '.join(p.unresolved)})" if p.unresolved else ""),
        data={
            "metric": p.metric,
            "filters": [f.model_dump(exclude_none=True) for f in p.filters],
            "breakdown": p.breakdown,
            "date_from": p.dates.date_from.isoformat(),
            "date_to": p.dates.date_to.isoformat(),
            "compare": p.dates.compare,
            "intent": p.intent,
            "unresolved": p.unresolved,
        },
    )


# --------------------------------------------------------------------------- registry

TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool(
            "get_metric_summary",
            "Value of one metric over a date window with the change versus the preceding window of equal "
            "length. "
            "Use this first for any 'what is / how did X change' question.",
            MetricSummaryArgs,
            _metric_summary,  # type: ignore[arg-type]
        ),
        Tool(
            "breakdown_metric",
            "Split a metric by one dimension for a window, with each segment's share of volume and change "
            "versus "
            "the preceding window. Use to find which segment moved.",
            BreakdownArgs,
            _breakdown,  # type: ignore[arg-type]
        ),
        Tool(
            "run_funnel",
            "Session funnel through ordered events with step and overall conversion; optionally broken down "
            "by a "
            "session dimension. Use for 'where do users drop off'.",
            FunnelArgs,
            _funnel,  # type: ignore[arg-type]
        ),
        Tool(
            "root_cause",
            "Decompose a metric change between a period and a baseline into segment (rate) and mix effects "
            "across "
            "all dimensions, and correlate with releases and experiments. Use for 'why did X change'.",
            RootCauseArgs,
            _root_cause,  # type: ignore[arg-type]
        ),
        Tool(
            "list_anomalies",
            "Anomalies detected by the monitor, most severe first.",
            AnomaliesArgs,
            _anomalies,
        ),  # type: ignore[arg-type]
        Tool(
            "list_releases",
            "Product releases in a window, with platform and affected areas.",
            ReleasesArgs,
            _releases,
        ),  # type: ignore[arg-type]
        Tool(
            "list_experiments",
            "Experiments with status, metrics and recorded decisions.",
            ExperimentsArgs,
            _experiments,
        ),  # type: ignore[arg-type]
        Tool(
            "experiment_results",
            "Full readout for one experiment: exposure, per-metric lift with intervals and p-values, "
            "guardrails and "
            "the rule-based recommendation.",
            ExperimentResultsArgs,
            _experiment_results,  # type: ignore[arg-type]
        ),
        Tool(
            "list_investigations",
            "Investigations with status, scope and hypotheses.",
            InvestigationsArgs,
            _investigations,
        ),  # type: ignore[arg-type]
        Tool(
            "search_knowledge",
            "Search SOPs, knowledge documents and the decision log.",
            SearchArgs,
            _search_knowledge,
        ),  # type: ignore[arg-type]
        Tool(
            "plan_query",
            "Parse a natural-language metric question into metric, filters, breakdown and dates using the "
            "known "
            "vocabulary. Use when unsure how a user's words map to metric or dimension keys.",
            PlanArgs,
            _plan,  # type: ignore[arg-type]
        ),
    ]
}


def run_tool(name: str, raw_args: dict[str, Any], ctx: ToolContext, call_id: str) -> ToolCallRecord:
    """Validate, execute and time one tool call. Never raises: errors become records."""
    t0 = time.perf_counter()
    tool = TOOLS.get(name)
    if tool is None:
        return ToolCallRecord(
            id=call_id, name=name, args=raw_args, summary="", ms=0, error=f"Unknown tool '{name}'"
        )
    try:
        args = tool.args_model.model_validate(raw_args)
    except ValidationError as exc:
        return ToolCallRecord(
            id=call_id,
            name=name,
            args=raw_args,
            summary="",
            ms=0,
            error=f"Invalid arguments: {exc.errors()[0]['msg']}",
        )
    try:
        result = tool.run(args, ctx)
    except Exception as exc:
        ms = int((time.perf_counter() - t0) * 1000)
        return ToolCallRecord(
            id=call_id,
            name=name,
            args=args.model_dump(mode="json", exclude_none=True),
            summary="",
            ms=ms,
            error=str(exc)[:300],
        )
    ms = int((time.perf_counter() - t0) * 1000)
    return ToolCallRecord(
        id=call_id,
        name=name,
        args=args.model_dump(mode="json", exclude_none=True),
        summary=result.summary,
        ms=ms,
        data=result.data,
    )
