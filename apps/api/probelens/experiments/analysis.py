"""Experiment readout: exposures, per-variant metrics, guardrails, timeline, segments.

Two kinds of experiment are analysed the same way:

* Experiments whose exposures were logged in the event stream (the seeded ones):
  a user's variant is whatever the `experiments` map says on their first exposure.
* Experiments created in the app after the fact: users are assigned by the same
  MD5 bucketing the SDK would use (`assignment.variant_case_sql`), applied to the
  audience active in the window. With no real treatment these read as A/A tests,
  which is exactly what they should do.

Outcomes are measured from each user's first exposure through `as_of`, so lagged
metrics (returns, deliveries) get their tail even after the experiment ends.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel

from probelens.analytics.dimensions import DIMENSIONS, Filter, Scope, compile_filters
from probelens.analytics.metrics import Metric, get_metric
from probelens.analytics.query import SESSION_ROLLUP_FIELDS
from probelens.analytics.sql import DATE_WINDOW, NOT_POST_PURCHASE
from probelens.db.clickhouse import run_query
from probelens.experiments import stats
from probelens.experiments.assignment import VariantSpec, variant_case_sql

SEGMENT_DIMENSIONS = ("platform", "user_type")
Role = Literal["primary", "guardrail"]
Direction = Literal["better", "worse", "flat"]


@dataclass(frozen=True)
class ExperimentSpec:
    """What the analysis needs to know about an experiment, decoupled from the ORM."""

    key: str
    variants: list[VariantSpec]
    control_key: str
    start: date
    end: date | None
    primary_metric: str
    guardrail_metrics: list[str]
    audience_filters: list[Filter]
    traffic_percent: int
    has_exposure_events: bool
    min_sample_per_variant: int
    min_relative_effect: float
    min_duration_days: int


# --------------------------------------------------------------------------- result models


class VariantStat(BaseModel):
    key: str
    users: int
    value: float | None
    numerator: float
    denominator: float
    ci_low: float | None
    ci_high: float | None


class VariantComparison(BaseModel):
    variant: str
    abs_diff: float
    rel_diff: float | None
    ci_low: float
    ci_high: float
    rel_ci_low: float | None
    rel_ci_high: float | None
    p_value: float
    significant: bool
    direction: Direction


class MetricReadout(BaseModel):
    metric_key: str
    label: str
    format: str
    higher_is_better: bool
    role: Role
    variants: list[VariantStat]
    comparisons: list[VariantComparison]


class Srm(BaseModel):
    chi2: float
    p_value: float
    mismatch: bool
    expected: dict[str, float]


class Exposure(BaseModel):
    total_users: int
    by_variant: dict[str, int]
    first_exposure: date | None
    last_exposure: date | None
    days_running: int
    contaminated_users: int
    srm: Srm | None


class TimelinePoint(BaseModel):
    day: date
    cumulative: dict[str, float | None]  # variant -> cumulative metric value
    users: dict[str, int]  # variant -> cumulative exposed users


class SegmentRow(BaseModel):
    segment: str
    users: int
    control: float | None
    treatment: float | None
    rel_diff: float | None
    p_value: float | None
    significant: bool


class SegmentReadout(BaseModel):
    dimension: str
    label: str
    rows: list[SegmentRow]


class Power(BaseModel):
    baseline: float | None
    required_n_per_variant: int | None
    smallest_variant_n: int
    detectable_effect_now: float | None
    users_per_day: float | None
    projected_days_to_power: int | None


class Check(BaseModel):
    name: str
    passed: bool
    detail: str


class Recommendation(BaseModel):
    decision: Literal["ship", "iterate", "stop", "continue"]
    confidence: Literal["low", "medium", "high"]
    headline: str
    reasons: list[str]
    risks: list[str]
    checks: list[Check]


class ExperimentResults(BaseModel):
    experiment_key: str
    as_of: date
    window_start: date
    window_end: date
    control: str
    exposure: Exposure
    metrics: list[MetricReadout]
    timeline: list[TimelinePoint]
    segments: list[SegmentReadout]
    power: Power
    recommendation: Recommendation
    notes: list[str]


# --------------------------------------------------------------------------- SQL


# A user's segment is whatever they were at first exposure, so each user lands in
# exactly one segment and the unit of analysis stays the user.
_SEGMENT_COLS = ",\n           ".join(
    f"argMin({DIMENSIONS[d].col}, timestamp) AS x_{DIMENSIONS[d].col}" for d in SEGMENT_DIMENSIONS
)


def _exposed_cte(spec: ExperimentSpec, params: dict[str, Any]) -> str:
    params["key"] = spec.key
    if spec.has_exposure_events:
        return f"""
exposed AS (
    SELECT user_id,
           argMin(experiments[{{key:String}}], timestamp) AS variant,
           min(timestamp) AS first_exposure,
           uniqExact(experiments[{{key:String}}]) AS n_variants,
           {_SEGMENT_COLS}
    FROM events
    WHERE event_date BETWEEN {{x_from:Date}} AND {{x_to:Date}} AND experiments[{{key:String}}] != ''
    GROUP BY user_id
)"""
    session_filters = [f for f in spec.audience_filters if f.dim.scope == Scope.session]
    where = compile_filters(session_filters, prefix="a")
    params.update(where.params)
    case = variant_case_sql("key", spec.variants, spec.traffic_percent)
    return f"""
exposed AS (
    SELECT user_id,
           {case} AS variant,
           min(timestamp) AS first_exposure,
           1 AS n_variants,
           {_SEGMENT_COLS}
    FROM events
    WHERE event_date BETWEEN {{x_from:Date}} AND {{x_to:Date}} AND {where.sql}
    GROUP BY user_id
    HAVING variant != ''
)"""


def _per_user_sql(m: Metric, spec: ExperimentSpec, params: dict[str, Any], segment: str | None = None) -> str:
    """Rows of (variant, user_id[, segment], num, den): one per exposed user."""
    cte = _exposed_cte(spec, params)
    seg_select = f", e.x_{DIMENSIONS[segment].col} AS segment" if segment else ""
    seg_group = ", segment" if segment else ""
    if m.scope == Scope.session:
        # Sessions that overlap or follow the user's first exposure; the exposure
        # session itself counts even when exposure happened mid-session.
        source = f"""
(SELECT {SESSION_ROLLUP_FIELDS}, max(timestamp) AS session_end
 FROM events
 WHERE {DATE_WINDOW} AND {NOT_POST_PURCHASE} AND events.user_id IN (SELECT user_id FROM exposed)
 GROUP BY session_id) AS s
INNER JOIN exposed AS e ON s.user_id = e.user_id
WHERE s.session_end >= e.first_exposure"""
        user_col = "s.user_id"
    else:
        source = f"""
events AS ev
INNER JOIN exposed AS e ON ev.user_id = e.user_id
WHERE {DATE_WINDOW} AND ev.timestamp >= e.first_exposure"""
        user_col = "ev.user_id"
    return f"""
WITH {cte}
SELECT e.variant AS variant, {user_col} AS uid{seg_select},
       {m.numerator} AS num, {m.denominator or "1"} AS den
FROM {source}
GROUP BY variant, uid{seg_group}"""


def _moments_sql(m: Metric, spec: ExperimentSpec, params: dict[str, Any], segment: str | None = None) -> str:
    inner = _per_user_sql(m, spec, params, segment)
    seg = ", segment" if segment else ""
    return f"""
SELECT variant{seg}, count() AS n, sum(num) AS sum_num, sum(den) AS sum_den,
       varSamp(num) AS var_num, varSamp(den) AS var_den, covarSamp(num, den) AS cov
FROM ({inner})
GROUP BY variant{seg}
ORDER BY variant{seg}"""


def _exposure_sql(spec: ExperimentSpec, params: dict[str, Any]) -> str:
    cte = _exposed_cte(spec, params)
    return f"""
WITH {cte}
SELECT variant, count() AS users, min(toDate(first_exposure)) AS first_day,
       max(toDate(first_exposure)) AS last_day, countIf(n_variants > 1) AS contaminated
FROM exposed
GROUP BY variant
ORDER BY variant"""


def _timeline_sql(m: Metric, spec: ExperimentSpec, params: dict[str, Any]) -> str:
    """Daily (variant, day, num, den, new users) for the primary metric."""
    cte = _exposed_cte(spec, params)
    if m.scope == Scope.session:
        source = f"""
(SELECT {SESSION_ROLLUP_FIELDS}, max(timestamp) AS session_end
 FROM events
 WHERE {DATE_WINDOW} AND {NOT_POST_PURCHASE} AND events.user_id IN (SELECT user_id FROM exposed)
 GROUP BY session_id) AS s
INNER JOIN exposed AS e ON s.user_id = e.user_id
WHERE s.session_end >= e.first_exposure"""
        day = "toDate(s.session_ts)"
    else:
        source = f"""
events AS ev
INNER JOIN exposed AS e ON ev.user_id = e.user_id
WHERE {DATE_WINDOW} AND ev.timestamp >= e.first_exposure"""
        day = "toDate(ev.timestamp)"
    return f"""
WITH {cte}
SELECT e.variant AS variant, {day} AS day, {m.numerator} AS num, {m.denominator or "1"} AS den
FROM {source}
GROUP BY variant, day
ORDER BY day, variant"""


def _new_users_sql(spec: ExperimentSpec, params: dict[str, Any]) -> str:
    cte = _exposed_cte(spec, params)
    return f"""
WITH {cte}
SELECT variant, toDate(first_exposure) AS day, count() AS users
FROM exposed
GROUP BY variant, day
ORDER BY day, variant"""


# --------------------------------------------------------------------------- analysis


def _moments(row: dict[str, Any]) -> stats.VariantMoments:
    return stats.VariantMoments(
        n=int(row["n"]),
        sum_num=float(row["sum_num"] or 0),
        sum_den=float(row["sum_den"] or 0),
        var_num=float(row["var_num"] or 0),
        var_den=float(row["var_den"] or 0),
        cov=float(row["cov"] or 0),
    )


def _direction(m: Metric, c: stats.Comparison) -> Direction:
    if not c.significant:
        return "flat"
    good = c.abs_diff > 0 if m.higher_is_better else c.abs_diff < 0
    return "better" if good else "worse"


def _readout(m: Metric, role: Role, rows: list[dict[str, Any]], control_key: str) -> MetricReadout:
    moments = {r["variant"]: _moments(r) for r in rows}
    variants: list[VariantStat] = []
    for key, mo in moments.items():
        var = mo.variance
        se = var**0.5 if var is not None else None
        variants.append(
            VariantStat(
                key=key,
                users=mo.n,
                value=mo.value,
                numerator=mo.sum_num,
                denominator=mo.sum_den,
                ci_low=(mo.value - stats.Z_95 * se) if mo.value is not None and se is not None else None,
                ci_high=(mo.value + stats.Z_95 * se) if mo.value is not None and se is not None else None,
            )
        )
    comparisons: list[VariantComparison] = []
    control = moments.get(control_key)
    if control is not None:
        for key, mo in moments.items():
            if key == control_key:
                continue
            c = stats.compare(control, mo)
            if c is None:
                continue
            comparisons.append(
                VariantComparison(
                    variant=key,
                    abs_diff=c.abs_diff,
                    rel_diff=c.rel_diff,
                    ci_low=c.ci_low,
                    ci_high=c.ci_high,
                    rel_ci_low=c.rel_ci_low,
                    rel_ci_high=c.rel_ci_high,
                    p_value=c.p_value,
                    significant=c.significant,
                    direction=_direction(m, c),
                )
            )
    return MetricReadout(
        metric_key=m.key,
        label=m.label,
        format=m.format.value,
        higher_is_better=m.higher_is_better,
        role=role,
        variants=variants,
        comparisons=comparisons,
    )


def _base_params(spec: ExperimentSpec, as_of: date) -> dict[str, Any]:
    end = min(spec.end or as_of, as_of)
    return {"x_from": spec.start, "x_to": end, "d_from": spec.start, "d_to": as_of}


def _exposure(spec: ExperimentSpec, as_of: date) -> Exposure:
    params = _base_params(spec, as_of)
    rows = run_query(_exposure_sql(spec, params), params, label=f"exp:{spec.key}:exposure")
    by_variant = {r["variant"]: int(r["users"]) for r in rows}
    first = min((_as_date(r["first_day"]) for r in rows), default=None)
    last = max((_as_date(r["last_day"]) for r in rows), default=None)
    contaminated = sum(int(r["contaminated"]) for r in rows)
    srm = None
    if len(by_variant) >= 2:
        weights = {v.key: v.weight for v in spec.variants}
        s = stats.sample_ratio_mismatch(by_variant, weights)
        srm = Srm(chi2=s.chi2, p_value=s.p_value, mismatch=s.mismatch, expected=s.expected)
    end = min(spec.end or as_of, as_of)
    days = (end - spec.start).days + 1 if end >= spec.start else 0
    return Exposure(
        total_users=sum(by_variant.values()),
        by_variant=by_variant,
        first_exposure=first,
        last_exposure=last,
        days_running=days,
        contaminated_users=contaminated,
        srm=srm,
    )


def _as_date(v: Any) -> date:
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _timeline(m: Metric, spec: ExperimentSpec, as_of: date) -> list[TimelinePoint]:
    params = _base_params(spec, as_of)
    rows = run_query(_timeline_sql(m, spec, params), params, label=f"exp:{spec.key}:timeline")
    params2 = _base_params(spec, as_of)
    new_rows = run_query(_new_users_sql(spec, params2), params2, label=f"exp:{spec.key}:new_users")
    variants = [v.key for v in spec.variants]
    days = sorted({_as_date(r["day"]) for r in rows} | {_as_date(r["day"]) for r in new_rows})
    num = dict.fromkeys(variants, 0.0)
    den = dict.fromkeys(variants, 0.0)
    users = dict.fromkeys(variants, 0)
    by_day: dict[date, list[dict[str, Any]]] = {}
    for r in rows:
        by_day.setdefault(_as_date(r["day"]), []).append(r)
    new_by_day: dict[date, list[dict[str, Any]]] = {}
    for r in new_rows:
        new_by_day.setdefault(_as_date(r["day"]), []).append(r)
    out: list[TimelinePoint] = []
    for d in days:
        for r in by_day.get(d, []):
            if r["variant"] in num:
                num[r["variant"]] += float(r["num"] or 0)
                den[r["variant"]] += float(r["den"] or 0)
        for r in new_by_day.get(d, []):
            if r["variant"] in users:
                users[r["variant"]] += int(r["users"])
        out.append(
            TimelinePoint(
                day=d,
                cumulative={v: (num[v] / den[v] if den[v] else None) for v in variants},
                users=dict(users),
            )
        )
    return out


def _segments(m: Metric, spec: ExperimentSpec, as_of: date, treatment_key: str) -> list[SegmentReadout]:
    out: list[SegmentReadout] = []
    for dim in SEGMENT_DIMENSIONS:
        params = _base_params(spec, as_of)
        rows = run_query(
            _moments_sql(m, spec, params, segment=dim), params, label=f"exp:{spec.key}:seg:{dim}"
        )
        by_seg: dict[str, dict[str, stats.VariantMoments]] = {}
        for r in rows:
            seg = str(r["segment"] or "unknown")
            by_seg.setdefault(seg, {})[r["variant"]] = _moments(r)
        seg_rows: list[SegmentRow] = []
        for seg, mo in sorted(by_seg.items(), key=lambda kv: -sum(x.n for x in kv[1].values())):
            control, treatment = mo.get(spec.control_key), mo.get(treatment_key)
            c = stats.compare(control, treatment) if control and treatment else None
            seg_rows.append(
                SegmentRow(
                    segment=seg,
                    users=sum(x.n for x in mo.values()),
                    control=control.value if control else None,
                    treatment=treatment.value if treatment else None,
                    rel_diff=c.rel_diff if c else None,
                    p_value=c.p_value if c else None,
                    significant=bool(c and c.significant),
                )
            )
        out.append(SegmentReadout(dimension=dim, label=DIMENSIONS[dim].label, rows=seg_rows))
    return out


def _power(
    primary: MetricReadout,
    spec: ExperimentSpec,
    exposure: Exposure,
    control_moments: stats.VariantMoments | None,
) -> Power:
    smallest = min(exposure.by_variant.values(), default=0)
    baseline = control_moments.value if control_moments else None
    per_user_var = None
    if control_moments and control_moments.variance is not None:
        per_user_var = control_moments.variance * control_moments.n
    required = (
        stats.required_n_per_variant(baseline, per_user_var, spec.min_relative_effect)
        if baseline and per_user_var
        else None
    )
    detectable = (
        stats.detectable_effect(baseline, per_user_var, smallest)
        if baseline and per_user_var and smallest
        else None
    )
    per_day = exposure.total_users / exposure.days_running if exposure.days_running else None
    projected = None
    if required is not None and per_day and smallest < required and len(spec.variants):
        share = min(v.weight for v in spec.variants) / sum(v.weight for v in spec.variants)
        projected = int((required - smallest) / max(per_day * share, 1e-9)) + 1
    return Power(
        baseline=baseline,
        required_n_per_variant=required,
        smallest_variant_n=smallest,
        detectable_effect_now=detectable,
        users_per_day=per_day,
        projected_days_to_power=projected,
    )


def analyze(spec: ExperimentSpec, as_of: date) -> ExperimentResults:
    from probelens.experiments.decision import recommend  # local import: decision depends on these models

    notes: list[str] = []
    exposure = _exposure(spec, as_of)
    treatment_key = next((v.key for v in spec.variants if v.key != spec.control_key), spec.control_key)

    metrics: list[MetricReadout] = []
    control_moments: stats.VariantMoments | None = None
    for i, key in enumerate([spec.primary_metric, *spec.guardrail_metrics]):
        m = get_metric(key)
        params = _base_params(spec, as_of)
        rows = run_query(_moments_sql(m, spec, params), params, label=f"exp:{spec.key}:{m.key}")
        role: Role = "primary" if i == 0 else "guardrail"
        metrics.append(_readout(m, role, rows, spec.control_key))
        if i == 0:
            control_row = next((r for r in rows if r["variant"] == spec.control_key), None)
            control_moments = _moments(control_row) if control_row else None

    primary_metric = get_metric(spec.primary_metric)
    timeline = _timeline(primary_metric, spec, as_of) if exposure.total_users else []
    segments = _segments(primary_metric, spec, as_of, treatment_key) if exposure.total_users else []
    power = _power(metrics[0], spec, exposure, control_moments)

    if not spec.has_exposure_events:
        notes.append(
            "No exposure events were logged for this experiment; users are assigned retroactively by "
            "deterministic hashing. Without a real treatment the readout should look like an A/A test."
        )
    if spec.end and as_of > spec.end:
        notes.append(
            "Exposures counted through "
            f"{spec.end.isoformat()}; outcomes measured through {as_of.isoformat()} "
            "so lagged metrics (returns, deliveries) include their tail."
        )
    if exposure.contaminated_users:
        notes.append(
            f"{exposure.contaminated_users} users were seen in "
            "more than one variant and are analysed under their first."
        )

    recommendation = recommend(spec, exposure, metrics, power, as_of)
    end = min(spec.end or as_of, as_of)
    return ExperimentResults(
        experiment_key=spec.key,
        as_of=as_of,
        window_start=spec.start,
        window_end=end,
        control=spec.control_key,
        exposure=exposure,
        metrics=metrics,
        timeline=timeline,
        segments=segments,
        power=power,
        recommendation=recommendation,
        notes=notes,
    )
