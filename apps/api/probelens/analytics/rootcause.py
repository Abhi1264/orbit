"""Root-cause analysis: which segments explain a metric change, and what shipped nearby.

Given a metric, an optional scope, an anomalous period and a baseline period, the
engine decomposes the period-over-baseline change across every applicable
dimension and ranks the segments that account for it. For ratio metrics the
decomposition separates a *rate* effect (the segment itself got worse) from a
*mix* effect (the segment simply became a bigger share of the denominator) so a
traffic-mix shift is never mistaken for a product regression.

Everything here is deterministic SQL + arithmetic. The AI analyst calls this as a
tool and narrates the result; it never invents numbers of its own.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from probelens.analytics.dimensions import DIMENSIONS, Filter, Scope
from probelens.analytics.metrics import Metric, get_metric
from probelens.analytics.query import MetricQuery, Series, run_metric_query
from probelens.models import Experiment, Release
from probelens.models.enums import ExperimentStatus, ReleaseStatus

SESSION_DIMS = [
    "platform",
    "app_version",
    "traffic_source",
    "user_type",
    "city_tier",
    "device_type",
    "country",
]
EVENT_DIMS = ["category", "subcategory", "payment_method", "payment_gateway"]
PAYMENT_METRICS = {"payment_success_rate", "payment_failure_rate", "payment_failures", "payment_attempts"}
RETURN_METRICS = {"return_rate", "returns"}
# Returns are attributed to the return date but lag the order by days; a dimension
# whose mix shifts inside that lag (an app rollout) produces meaningless ratios.
LAG_UNSAFE_DIMS = {"app_version"}
MIN_SEGMENT_SHARE = 0.02  # ignore slivers: they cannot explain a store-wide move


class Change(BaseModel):
    baseline: float | None
    period: float | None
    abs_change: float | None
    rel_change: float | None
    baseline_numerator: float
    baseline_denominator: float | None
    period_numerator: float
    period_denominator: float | None


class Contribution(BaseModel):
    key: str
    label: str
    baseline: float | None
    period: float | None
    rel_change: float | None
    share_baseline: float
    share_period: float
    # Fraction of the overall change attributable to this segment (can exceed 1 or
    # be negative when other segments moved the opposite way).
    explained: float | None
    rate_effect: float | None = None
    mix_effect: float | None = None
    # Segment had no volume in the baseline (a new app version, a new campaign).
    is_new: bool = False


class DimensionBreakdown(BaseModel):
    dimension: str
    label: str
    contributions: list[Contribution]
    # How concentrated the change is: the best single segment's explained share,
    # discounted for segments that are simply most of the volume.
    concentration: float
    # False when a session can belong to several segments (event dimensions on a
    # session metric): rates per segment are valid, but they do not sum to the total.
    additive: bool = True


class SupportingBreakdown(BaseModel):
    title: str
    dimension: str
    rows: list[dict[str, Any]]


class ReleaseRef(BaseModel):
    id: int
    version: str
    name: str
    platform: str
    release_date: date
    status: str
    days_before_period: int
    affected_areas: list[str]
    relevance: Literal["strong", "possible", "weak"]
    reason: str


class ExperimentRef(BaseModel):
    id: int
    key: str
    name: str
    status: str
    start_date: date
    end_date: date | None
    primary_metric: str
    guardrail_metrics: list[str]
    relevance: Literal["strong", "possible", "weak"]
    reason: str


class Candidate(BaseModel):
    rank: int
    kind: Literal["segment", "release", "experiment", "mix_shift"]
    title: str
    summary: str
    confidence: Literal["low", "medium", "high"]
    dimension: str | None = None
    key: str | None = None
    explained: float | None = None
    filters: list[Filter] = Field(default_factory=list)
    drill: list[Contribution] = Field(default_factory=list)
    drill_dimension: str | None = None
    release_id: int | None = None
    experiment_id: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class RootCauseAnalysis(BaseModel):
    metric: dict[str, Any]
    filters: list[str]
    period: dict[str, str]
    baseline: dict[str, str]
    overall: Change
    candidates: list[Candidate]
    dimensions: list[DimensionBreakdown]
    supporting: list[SupportingBreakdown]
    releases: list[ReleaseRef]
    experiments: list[ExperimentRef]
    notes: list[str]


# --------------------------------------------------------------------------- math


def _rel(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or a == 0:
        return None
    return (b - a) / a


def _change(series: Series, m: Metric, period_days: int, baseline_days: int) -> Change:
    base = series.compare_total
    per = series.total
    b_val = base.value if base else None
    p_val = per.value
    if m.denominator is None and b_val is not None and p_val is not None:
        # Volume metrics are compared per day so unequal windows do not mislead.
        b_val = b_val / baseline_days
        p_val = p_val / period_days
    return Change(
        baseline=b_val,
        period=p_val,
        abs_change=None if b_val is None or p_val is None else p_val - b_val,
        rel_change=_rel(b_val, p_val),
        baseline_numerator=base.numerator if base else 0,
        baseline_denominator=base.denominator if base else None,
        period_numerator=per.numerator,
        period_denominator=per.denominator,
    )


def _decompose(
    m: Metric, overall: Change, series: list[Series], period_days: int, baseline_days: int
) -> list[Contribution]:
    out: list[Contribution] = []
    total_change = overall.abs_change or 0.0
    is_ratio = m.denominator is not None

    if is_ratio:
        # Shares are of the denominator (sessions, attempts, orders...).
        base_den = sum((s.compare_total.denominator or 0) for s in series if s.compare_total)
        per_den = sum((s.total.denominator or 0) for s in series)
    else:
        base_den = sum((s.compare_total.numerator if s.compare_total else 0) for s in series)
        per_den = sum(s.total.numerator for s in series)

    for s in series:
        base = s.compare_total
        b_val = base.value if base else None
        p_val = s.total.value
        is_new = False
        if is_ratio:
            share_b = ((base.denominator or 0) / base_den) if base and base_den else 0.0
            share_p = ((s.total.denominator or 0) / per_den) if per_den else 0.0
            rate_effect = mix_effect = explained = None
            if b_val is None and share_b == 0 and p_val is not None and overall.baseline is not None:
                # A segment that did not exist before: everything it does is a rate
                # effect relative to how the average segment behaved in the baseline.
                is_new = True
                rate_effect = share_p * (p_val - overall.baseline)
                mix_effect = 0.0
                explained = rate_effect / total_change if total_change else None
            elif b_val is not None and p_val is not None:
                rate_effect = share_p * (p_val - b_val)
                mix_effect = (share_p - share_b) * (b_val - (overall.baseline or 0))
                explained = (rate_effect + mix_effect) / total_change if total_change else None
        else:
            b_day = (base.numerator / baseline_days) if base else 0.0
            p_day = s.total.numerator / period_days
            share_b = (base.numerator / base_den) if base and base_den else 0.0
            share_p = (s.total.numerator / per_den) if per_den else 0.0
            b_val, p_val = b_day, p_day
            rate_effect = mix_effect = None
            explained = ((p_day - b_day) / total_change) if total_change else None
        out.append(
            Contribution(
                key=s.key,
                label=s.label,
                baseline=b_val,
                period=p_val,
                rel_change=_rel(b_val, p_val),
                share_baseline=share_b,
                share_period=share_p,
                explained=explained,
                rate_effect=rate_effect,
                mix_effect=mix_effect,
                is_new=is_new,
            )
        )
    out.sort(key=lambda c: -abs(c.explained or 0))
    return out


def _describe_non_additive(m: Metric, overall: Change, series: list[Series]) -> list[Contribution]:
    """Per-segment rates without contributions, for overlapping segments."""
    is_ratio = m.denominator is not None
    per_den = sum(((s.total.denominator if is_ratio else s.total.numerator) or 0) for s in series) or 1
    base_den = (
        sum(
            ((s.compare_total.denominator if is_ratio else s.compare_total.numerator) or 0)
            for s in series
            if s.compare_total
        )
        or 1
    )
    out: list[Contribution] = []
    for s in series:
        base = s.compare_total
        b_val = base.value if base else None
        p_val = s.total.value
        b_vol = ((base.denominator if is_ratio else base.numerator) or 0) if base else 0
        p_vol = (s.total.denominator if is_ratio else s.total.numerator) or 0
        out.append(
            Contribution(
                key=s.key,
                label=s.label,
                baseline=b_val,
                period=p_val,
                rel_change=_rel(b_val, p_val),
                share_baseline=b_vol / base_den,
                share_period=p_vol / per_den,
                explained=None,
            )
        )
    overall_rel = overall.rel_change or 0.0
    out.sort(key=lambda c: -_excess(c, overall_rel))
    return out


def _excess(c: Contribution, overall_rel: float) -> float:
    """How much more than the average a segment moved, in the same direction, weighted by size."""
    if c.rel_change is None or c.share_period < 0.05:
        return 0.0
    same_direction = (c.rel_change < 0) == (overall_rel < 0)
    if not same_direction or abs(c.rel_change) <= abs(overall_rel):
        return 0.0
    return (abs(c.rel_change) - abs(overall_rel)) * c.share_period


def _concentration(contribs: list[Contribution], additive: bool = True, overall_rel: float = 0.0) -> float:
    if not additive:
        return max((_excess(c, overall_rel) for c in contribs), default=0.0)
    best = 0.0
    for c in contribs:
        if c.explained is None or c.share_period < MIN_SEGMENT_SHARE:
            continue
        # A segment that is 95% of volume explaining 95% of the change tells us nothing.
        best = max(best, c.explained * (1 - c.share_period))
    return best


UNIFORM_MIN_SHARE = 0.10  # segments smaller than this are too noisy to judge uniformity
UNIFORM_TOLERANCE = 0.35  # a segment is "in line" if its relative move is within ±35% of overall


def _uniform_dimensions(
    breakdowns: list[DimensionBreakdown], overall_rel: float
) -> tuple[list[str], list[str]]:
    """(uniform, judgeable): additive dimensions with at least two sizeable segments, and
    the subset on which every such segment moved in line with the overall change."""
    uniform: list[str] = []
    judgeable: list[str] = []
    if abs(overall_rel) < 0.05:
        return uniform, judgeable
    for b in breakdowns:
        if not b.additive:
            continue
        big = [c for c in b.contributions if c.share_period >= UNIFORM_MIN_SHARE and not c.is_new]
        if len(big) < 2 or any(c.rel_change is None for c in big):
            continue
        judgeable.append(b.dimension)
        in_line = all(
            abs((c.rel_change or 0.0) - overall_rel) <= UNIFORM_TOLERANCE * abs(overall_rel) for c in big
        )
        if in_line:
            uniform.append(b.dimension)
    return uniform, judgeable


# --------------------------------------------------------------------------- queries


def _breakdown(
    m: Metric,
    filters: list[Filter],
    dimension: str,
    period: tuple[date, date],
    baseline: tuple[date, date],
    limit: int = 12,
) -> list[Series]:
    result = run_metric_query(
        MetricQuery(
            metric=m.key,
            date_from=period[0],
            date_to=period[1],
            filters=filters,
            breakdown=dimension,
            granularity=None,
            compare_from=baseline[0],
            compare_to=baseline[1],
            limit=limit,
        )
    )
    return result.series


def _applicable_dimensions(m: Metric, filters: list[Filter]) -> list[tuple[str, bool]]:
    """(dimension, additive) pairs worth decomposing for this metric and scope."""
    fixed = {f.dimension for f in filters if f.operator == "eq"}
    dims: list[tuple[str, bool]] = [(d, True) for d in SESSION_DIMS]
    if m.scope == Scope.event:
        dims += [(d, True) for d in EVENT_DIMS]
    else:
        # Event dimensions on a session metric: a session touching two categories
        # counts in both, so rates are comparable but contributions are not.
        dims += [("category", False), ("subcategory", False)]
    if m.key not in PAYMENT_METRICS:
        dims = [(d, a) for d, a in dims if d not in ("payment_method", "payment_gateway")]
    if m.key in RETURN_METRICS:
        dims = [(d, a) for d, a in dims if d not in LAG_UNSAFE_DIMS]
    if m.denominator is None:
        # Users migrate between versions; for volumes that churn always "explains"
        # the total without meaning anything.
        dims = [(d, a) for d, a in dims if d != "app_version"]
    return [(d, a) for d, a in dims if d not in fixed]


def _supporting(m: Metric, filters: list[Filter], period, baseline) -> list[SupportingBreakdown]:
    """Reason mixes: not a decomposition of the metric, but the fastest way to
    tell an outage ('gateway_timeout') from a checkout UX problem ('user_abandoned')."""
    out: list[SupportingBreakdown] = []
    spec: list[tuple[str, str, str]] = []
    if m.key in PAYMENT_METRICS:
        spec.append(("payment_failures", "failure_reason", "Payment failures by reason"))
    if m.key in RETURN_METRICS:
        spec.append(("returns", "return_reason", "Returns by stated reason"))
    for metric_key, dim, title in spec:
        series = _breakdown(get_metric(metric_key), filters, dim, period, baseline, limit=8)
        base_total = sum((s.compare_total.numerator if s.compare_total else 0) for s in series) or 1
        per_total = sum(s.total.numerator for s in series) or 1
        rows = [
            {
                "key": s.key,
                "label": s.label,
                "baseline_count": s.compare_total.numerator if s.compare_total else 0,
                "period_count": s.total.numerator,
                "baseline_share": (s.compare_total.numerator if s.compare_total else 0) / base_total,
                "period_share": s.total.numerator / per_total,
            }
            for s in series
        ]
        rows.sort(key=lambda r: -(r["period_share"] - r["baseline_share"]))
        out.append(SupportingBreakdown(title=title, dimension=dim, rows=rows))
    return out


# --------------------------------------------------------------------------- context


def _platform_of(filters: list[Filter], candidates: list[Candidate]) -> set[str]:
    platforms = {str(f.value) for f in filters if f.dimension == "platform" and f.operator == "eq"}
    for c in candidates:
        if c.dimension == "platform" and c.key:
            platforms.add(c.key)
    return platforms


def _releases(
    db: Session, m: Metric, period: tuple[date, date], platforms: set[str], versions: set[str]
) -> list[ReleaseRef]:
    lo, hi = period[0] - timedelta(days=10), period[1]
    rows = db.scalars(
        select(Release)
        .where(Release.release_date >= lo, Release.release_date <= hi)
        .order_by(Release.release_date)
    )
    out: list[ReleaseRef] = []
    for r in rows:
        if r.status == ReleaseStatus.planned:
            continue
        days_before = (period[0] - r.release_date).days
        area_hit = _areas_touch_metric(m, list(r.affected_areas or []))
        platform_hit = r.platform == "all" or r.platform in platforms or not platforms
        if r.version in versions:
            relevance, reason = (
                "strong",
                f"Version {r.version} is itself one of the segments explaining the change",
            )
        elif area_hit and platform_hit and -3 <= days_before <= 10:
            relevance, reason = (
                "strong",
                f"Touches {', '.join(r.affected_areas)} and shipped {_days_phrase(days_before)}",
            )
        elif area_hit or (platform_hit and -3 <= days_before <= 10):
            relevance, reason = "possible", f"Shipped {_days_phrase(days_before)} on {r.platform}"
        else:
            relevance, reason = (
                "weak",
                f"In window but touches unrelated areas ({', '.join(r.affected_areas) or 'none'})",
            )
        out.append(
            ReleaseRef(
                id=r.id,
                version=r.version,
                name=r.name,
                platform=r.platform,
                release_date=r.release_date,
                status=r.status.value,
                days_before_period=days_before,
                affected_areas=list(r.affected_areas or []),
                relevance=relevance,
                reason=reason,
            )
        )
    order = {"strong": 0, "possible": 1, "weak": 2}
    out.sort(key=lambda r: (order[r.relevance], -r.days_before_period))
    return out


def _areas_touch_metric(m: Metric, areas: list[str]) -> bool:
    touch = {
        "checkout": {"conversion", "checkout_conversion", "orders", "revenue", "aov"} | PAYMENT_METRICS,
        "payments": PAYMENT_METRICS | {"conversion", "checkout_conversion", "orders", "revenue"},
        "search": {
            "search_to_product_view_rate",
            "searches",
            "product_views",
            "conversion",
            "add_to_cart_rate",
        },
        "discovery": {
            "search_to_product_view_rate",
            "product_views",
            "add_to_cart_rate",
            "conversion",
            "bounce_rate",
        },
        "pdp": {"add_to_cart_rate", "product_views", "conversion"},
        "wishlist": set(),
    }
    return any(m.key in touch.get(a, set()) for a in areas)


def _days_phrase(days_before: int) -> str:
    if days_before > 0:
        return f"{days_before} day{'s' if days_before != 1 else ''} before the period started"
    if days_before == 0:
        return "on the first day of the period"
    return f"{-days_before} day{'s' if days_before != -1 else ''} into the period"


def _experiments(db: Session, m: Metric, period: tuple[date, date]) -> list[ExperimentRef]:
    rows = db.scalars(
        select(Experiment).where(
            Experiment.start_date <= period[1],
            (Experiment.end_date.is_(None)) | (Experiment.end_date >= period[0] - timedelta(days=3)),
            Experiment.status != ExperimentStatus.draft,
        )
    )
    out: list[ExperimentRef] = []
    for e in rows:
        guardrails = list(e.guardrail_metrics or [])
        if e.primary_metric == m.key:
            relevance, reason = "strong", "This metric is the experiment's primary metric"
        elif m.key in guardrails:
            relevance, reason = "strong", "This metric is a guardrail for the experiment"
        elif abs((e.start_date - period[0]).days) <= 5:
            relevance, reason = "possible", "Started within a few days of the period"
        else:
            relevance, reason = "weak", "Running during the period"
        out.append(
            ExperimentRef(
                id=e.id,
                key=e.key,
                name=e.name,
                status=e.status.value,
                start_date=e.start_date,
                end_date=e.end_date,
                primary_metric=e.primary_metric,
                guardrail_metrics=guardrails,
                relevance=relevance,
                reason=reason,
            )
        )
    order = {"strong": 0, "possible": 1, "weak": 2}
    out.sort(key=lambda r: order[r.relevance])
    return out


# --------------------------------------------------------------------------- narrative


def _fmt(m: Metric, v: float | None) -> str:
    if v is None:
        return "n/a"
    f = m.format.value
    if f == "percent":
        return f"{v * 100:.1f}%"
    if f == "currency":
        return f"₹{v:,.0f}"
    if f == "days":
        return f"{v:.1f} days"
    return f"{v:,.0f}"


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v * 100:+.0f}%"


def _segment_candidate(
    m: Metric,
    overall: Change,
    dim: str,
    c: Contribution,
    filters: list[Filter],
    period: tuple[date, date],
    baseline: tuple[date, date],
) -> Candidate:
    explained = c.explained or 0.0
    overall_rel = overall.rel_change or 0.0
    # A new segment has no own baseline; compare its level with the baseline average.
    seg_rel = (_rel(overall.baseline, c.period) if c.is_new else c.rel_change) or 0.0
    isolated = abs(seg_rel) >= 1.5 * abs(overall_rel) and c.share_period < 0.7
    # "Explains 66% while being 65% of volume" is not a lead; discount by size.
    informativeness = explained * (1 - c.share_period)
    if explained >= 0.6 and isolated:
        confidence = "high"
    elif (explained >= 0.35 and informativeness >= 0.25) or (isolated and explained >= 0.2):
        confidence = "medium"
    else:
        confidence = "low"

    dim_label = DIMENSIONS[dim].label
    others = "other segments were broadly flat" if isolated else "other segments moved too"
    if c.is_new:
        summary = (
            f"{dim_label} = {c.label} is new in this period and accounts for {explained * 100:.0f}% of the "
            f"{m.label.lower()} change. It runs at {_fmt(m, c.period)} against a baseline average of "
            f"{_fmt(m, overall.baseline)} ({_pct(seg_rel)}) and is {c.share_period * 100:.0f}% of volume; "
            f"{others}."
        )
    else:
        summary = (
            f"{dim_label} = {c.label} accounts for {explained * 100:.0f}% of the {m.label.lower()} change. "
            f"Within the segment the metric went from {_fmt(m, c.baseline)} to {_fmt(m, c.period)} "
            f"({_pct(c.rel_change)}) while its share of volume was {c.share_period * 100:.0f}%; {others}."
        )
    if c.mix_effect is not None and c.rate_effect is not None and abs(c.mix_effect) > abs(c.rate_effect):
        summary += " Most of this is a mix effect: the segment's share changed more than its own rate."

    seg_value: str | int = int(c.key) if DIMENSIONS[dim].ch_type == "UInt32" else c.key
    scoped = [*filters, Filter(dimension=dim, operator="eq", value=seg_value)]
    drill_dim, drill = _drill(m, scoped, dim, period, baseline)
    return Candidate(
        rank=0,
        kind="segment",
        title=f"{dim_label}: {c.label}",
        summary=summary,
        confidence=confidence,
        dimension=dim,
        key=c.key,
        explained=explained,
        filters=scoped,
        drill=drill,
        drill_dimension=drill_dim,
        data={**c.model_dump(), "isolated": isolated, "informativeness": informativeness},
    )


def _overlap_candidate(
    m: Metric, overall: Change, dim: str, c: Contribution, filters: list[Filter]
) -> Candidate:
    """Candidate from a non-additive dimension: the segment moved far more than average."""
    dim_label = DIMENSIONS[dim].label
    ratio = abs(c.rel_change or 0) / abs(overall.rel_change or 1e-9)
    confidence = "high" if ratio >= 3 and c.share_period >= 0.15 else "medium"
    summary = (
        f"Sessions touching {dim_label.lower()} = {c.label} saw {m.label.lower()} move from "
        f"{_fmt(m, c.baseline)} to {_fmt(m, c.period)} ({_pct(c.rel_change)}), roughly {ratio:.1f}× the "
        f"overall move ({_pct(overall.rel_change)}). They are {c.share_period * 100:.0f}% of sessions. "
        f"Sessions can span several {dim_label.lower()} values, so this is a comparison of rates, not a "
        f"share of the total change."
    )
    seg_value: str | int = int(c.key) if DIMENSIONS[dim].ch_type == "UInt32" else c.key
    return Candidate(
        rank=0,
        kind="segment",
        title=f"{dim_label}: {c.label}",
        summary=summary,
        confidence=confidence,
        dimension=dim,
        key=c.key,
        explained=None,
        filters=[*filters, Filter(dimension=dim, operator="eq", value=seg_value)],
        data=c.model_dump(),
    )


def _drill(
    m: Metric, filters: list[Filter], skip_dim: str, period, baseline
) -> tuple[str | None, list[Contribution]]:
    """One level deeper inside the top segment: which sub-segment carries it?"""
    best_dim: str | None = None
    best: list[Contribution] = []
    best_score = 0.0
    total = _scope_total(m, filters, period, baseline)
    for dim, additive in _applicable_dimensions(m, filters):
        if dim == skip_dim or not additive:
            continue
        series = _breakdown(m, filters, dim, period, baseline, limit=8)
        if len(series) < 2:
            continue
        contribs = _decompose(m, total, series, _days(period), _days(baseline))
        score = _concentration(contribs)
        if score > best_score:
            best_score, best_dim, best = score, dim, contribs[:5]
    return best_dim, best


def _scope_total(m: Metric, filters: list[Filter], period, baseline) -> Change:
    series = run_metric_query(
        MetricQuery(
            metric=m.key,
            date_from=period[0],
            date_to=period[1],
            filters=filters,
            granularity=None,
            compare_from=baseline[0],
            compare_to=baseline[1],
        )
    ).series[0]
    return _change(series, m, _days(period), _days(baseline))


def _days(window: tuple[date, date]) -> int:
    return (window[1] - window[0]).days + 1


def _mix_shift_candidate(
    m: Metric, overall: Change, breakdowns: list[DimensionBreakdown]
) -> Candidate | None:
    """When the overall change is mostly a mix effect, say so up front."""
    if not overall.abs_change:
        return None
    for b in breakdowns:
        top = b.contributions[0] if b.contributions else None
        if top is None or top.mix_effect is None or top.rate_effect is None:
            continue
        mix_share = top.mix_effect / overall.abs_change
        if abs(top.mix_effect) > abs(top.rate_effect) and abs(mix_share) >= 0.5:
            return Candidate(
                rank=0,
                kind="mix_shift",
                title=f"Mix shift in {b.label.lower()}",
                summary=(
                    f"{b.label} = {top.label} moved from {top.share_baseline * 100:.0f}% to "
                    f"{top.share_period * 100:.0f}% of volume. Because its own {m.label.lower()} "
                    f"({_fmt(m, top.baseline)}) differs from the average, the shift alone explains "
                    f"{abs(mix_share) * 100:.0f}% of the change."
                ),
                confidence="medium",
                dimension=b.dimension,
                key=top.key,
                explained=mix_share,
                data=top.model_dump(),
            )
    return None


# --------------------------------------------------------------------------- entrypoint


def analyze(
    db: Session,
    *,
    metric_key: str,
    filters: list[Filter],
    period_start: date,
    period_end: date,
    baseline_start: date,
    baseline_end: date,
) -> RootCauseAnalysis:
    m = get_metric(metric_key)
    period = (period_start, period_end)
    baseline = (baseline_start, baseline_end)
    notes: list[str] = []

    overall = _scope_total(m, filters, period, baseline)
    if overall.abs_change is None:
        notes.append("Metric has no value in one of the windows; contributions cannot be computed.")

    if m.key in RETURN_METRICS:
        notes.append(
            "Return rate attributes returns to the day they were initiated, so it lags orders by "
            "3–14 days. App version is excluded from the decomposition because its mix shifts "
            "inside that lag."
        )

    breakdowns: list[DimensionBreakdown] = []
    overall_rel = overall.rel_change or 0.0
    for dim, additive in _applicable_dimensions(m, filters):
        series = _breakdown(m, filters, dim, period, baseline)
        if len(series) < 2:
            continue
        if additive:
            contribs = _decompose(m, overall, series, _days(period), _days(baseline))
        else:
            contribs = _describe_non_additive(m, overall, series)
        breakdowns.append(
            DimensionBreakdown(
                dimension=dim,
                label=DIMENSIONS[dim].label,
                contributions=contribs,
                concentration=_concentration(contribs, additive, overall_rel),
                additive=additive,
            )
        )
    breakdowns.sort(key=lambda b: -b.concentration)

    # When every sizeable segment on every additive dimension moved by about the
    # same relative amount, slicing cannot find the cause: it is scope-wide.
    # Listing "android explains 53%" would only reflect that android is 53% of
    # volume, so those slices are dropped and the analysis says so instead.
    uniform, judgeable = _uniform_dimensions(breakdowns, overall_rel)
    scope_wide = len(judgeable) >= 2 and len(uniform) == len(judgeable)

    candidates: list[Candidate] = []
    seen_keys: set[tuple[str, str]] = set()
    for b in [x for x in breakdowns if x.additive][:4]:
        if scope_wide:
            break
        for c in b.contributions[:2]:
            if c.explained is None or c.share_period < MIN_SEGMENT_SHARE:
                continue
            if abs(c.explained) < 0.2 or (b.dimension, c.key) in seen_keys:
                continue
            seen_keys.add((b.dimension, c.key))
            candidates.append(_segment_candidate(m, overall, b.dimension, c, filters, period, baseline))
    for b in [x for x in breakdowns if not x.additive]:
        for c in b.contributions[:1]:
            if _excess(c, overall_rel) <= 0 or c.rel_change is None:
                continue
            if abs(c.rel_change) < 2 * abs(overall_rel) or c.share_period < 0.1:
                continue
            candidates.append(_overlap_candidate(m, overall, b.dimension, c, filters))
    mix = _mix_shift_candidate(m, overall, breakdowns)
    if mix:
        candidates.append(mix)

    platforms = _platform_of(filters, candidates)
    version_candidates = {
        c.key: c for c in candidates if c.kind == "segment" and c.dimension == "app_version" and c.key
    }
    # A version that swept to most of the volume during the period never shows up as a
    # segment (it *is* the volume), but the mix-shift candidate names it.
    mix_versions = {
        c.key for c in candidates if c.kind == "mix_shift" and c.dimension == "app_version" and c.key
    }
    scoped_platforms = {str(f.value) for f in filters if f.dimension == "platform" and f.operator == "eq"}
    releases = _releases(db, m, period, platforms, set(version_candidates))
    experiments = _experiments(db, m, period)

    lead_platforms = {
        c.key
        for c in candidates
        if c.kind == "segment" and c.dimension == "platform" and c.confidence in ("high", "medium")
    }
    for r in releases:
        if r.relevance != "strong":
            continue
        if lead_platforms and r.platform != "all" and r.platform not in lead_platforms:
            continue  # same version shipped on a platform the evidence does not implicate
        version_hit = version_candidates.get(r.version)
        strong_platform = any(
            c.kind == "segment"
            and c.dimension == "platform"
            and c.key == r.platform
            and c.confidence == "high"
            for c in candidates
        )
        if version_hit is not None:
            # The release is only as convincing as the evidence its version segment carries.
            confidence = version_hit.confidence
        elif r.version in mix_versions and (strong_platform or r.platform in scoped_platforms):
            # The version rolled out across the scope during the period and carries a worse
            # rate; with the scope already pinned to its platform that is a real lead, and a
            # tight timing match makes it the leading one.
            confidence = "high" if 0 <= r.days_before_period <= 7 else "medium"
        elif strong_platform or (r.platform == "all" and -3 <= r.days_before_period <= 3):
            confidence = "medium"
        else:
            confidence = "low"
        summary = f"{r.name}: {r.reason}."
        mix_hit = next((x for x in candidates if x.kind == "mix_shift" and x.key == r.version), None)
        if version_hit is None and mix_hit is not None:
            summary += (
                f" Version {r.version} went from {mix_hit.data['share_baseline'] * 100:.0f}% to "
                f"{mix_hit.data['share_period'] * 100:.0f}% of volume during the period and runs at "
                f"{_fmt(m, mix_hit.data['period'])} against a baseline of {_fmt(m, overall.baseline)}."
            )
        candidates.append(
            Candidate(
                rank=0,
                kind="release",
                title=f"Release {r.version} ({r.platform})",
                summary=summary,
                confidence=confidence,
                release_id=r.id,
                explained=version_hit.explained if version_hit else None,
                data=r.model_dump(mode="json"),
            )
        )
    for e in experiments:
        if e.relevance == "strong":
            candidates.append(
                Candidate(
                    rank=0,
                    kind="experiment",
                    title=f"Experiment: {e.name}",
                    summary=f"{e.reason}. Check the variant split before attributing the move elsewhere.",
                    confidence="low",
                    experiment_id=e.id,
                    data=e.model_dump(mode="json"),
                )
            )

    order = {"high": 0, "medium": 1, "low": 2}

    def _strength(c: Candidate) -> float:
        if "informativeness" in c.data:
            return abs(float(c.data["informativeness"]))
        if c.kind == "release":
            # Rank a release by the evidence behind it, not by the raw share of the
            # change its version happens to carry (a big version carries a big share).
            version = str(c.data.get("version", ""))
            hit = version_candidates.get(version) or next(
                (x for x in candidates if x.kind == "mix_shift" and x.key == version), None
            )
            return _strength(hit) if hit else 0.0
        return abs(c.explained) if c.explained is not None else 0.0

    candidates.sort(key=lambda c: (order[c.confidence], -_strength(c)))
    if any(c.confidence != "low" for c in candidates):
        # Once there is a real lead, proportional slices only add noise; keep two for context.
        strong = [c for c in candidates if c.confidence != "low"]
        weak = [c for c in candidates if c.confidence == "low"]
        candidates = strong + weak[:2]
    for i, c in enumerate(candidates, start=1):
        c.rank = i

    if scope_wide:
        dims = ", ".join(DIMENSIONS[d].label.lower() for d in uniform)
        scope = " within " + " and ".join(f.describe() for f in filters) if filters else ""
        notes.append(
            f"Every sizeable segment moved by a similar amount across {dims}{scope}. The cause is "
            "scope-wide rather than a sub-segment: look at what changed for the whole scope (traffic "
            "quality, a campaign, pricing, a store-wide release) instead of drilling further."
        )
    elif not candidates:
        notes.append("No single segment explains the change; it looks broad-based.")
    if _days(period) < 3:
        notes.append("Period is under three days; treat rates as noisy.")

    return RootCauseAnalysis(
        metric={
            "key": m.key,
            "label": m.label,
            "format": m.format.value,
            "higher_is_better": m.higher_is_better,
        },
        filters=[f.describe() for f in filters],
        period={"start": period_start.isoformat(), "end": period_end.isoformat()},
        baseline={"start": baseline_start.isoformat(), "end": baseline_end.isoformat()},
        overall=overall,
        candidates=candidates[:8],
        dimensions=breakdowns,
        supporting=_supporting(m, filters, period, baseline),
        releases=releases,
        experiments=experiments,
        notes=notes,
    )
