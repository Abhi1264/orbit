"""Metric query engine: compiles a MetricQuery into ClickHouse SQL and shapes results."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from probelens.analytics.dimensions import DIMENSIONS, Filter, Scope, compile_filters
from probelens.analytics.metrics import METRICS, Metric, MetricFormat, get_metric
from probelens.analytics.sql import DATE_WINDOW, session_where
from probelens.db.clickhouse import run_query

Granularity = Literal["hour", "day", "week"]

SESSION_DIM_COLS = [d.key for d in DIMENSIONS.values() if d.scope == Scope.session]

SESSION_ROLLUP_FIELDS = """
    session_id,
    min(timestamp) AS session_ts,
    any(user_id) AS user_id,
    {session_dims},
    count() AS event_count,
    max(event_name = 'search') AS has_search,
    max(event_name = 'product_view') AS has_pv,
    max(event_name = 'add_to_cart') AS has_atc,
    max(event_name = 'checkout_started') AS has_checkout,
    max(event_name = 'payment_started') AS has_payment,
    max(event_name = 'order_completed') AS has_order
""".format(session_dims=",\n    ".join(f"any({c}) AS s_{c}" for c in SESSION_DIM_COLS))

class MetricQuery(BaseModel):
    metric: str
    date_from: date
    date_to: date
    filters: list[Filter] = Field(default_factory=list)
    breakdown: str | None = None
    granularity: Granularity | None = "day"
    compare_from: date | None = None
    compare_to: date | None = None
    limit: int = Field(default=8, ge=1, le=50)

    @model_validator(mode="after")
    def _check(self) -> "MetricQuery":
        if self.metric not in METRICS:
            raise ValueError(f"Unknown metric '{self.metric}'")
        if self.breakdown is not None and self.breakdown not in DIMENSIONS:
            raise ValueError(f"Unknown dimension '{self.breakdown}'")
        if self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        if (self.compare_from is None) != (self.compare_to is None):
            raise ValueError("compare_from and compare_to must be given together")
        if (self.date_to - self.date_from).days > 400:
            raise ValueError("Date range too large")
        return self

    def describe(self) -> dict[str, Any]:
        m = get_metric(self.metric)
        return {
            "metric": m.label,
            "metric_key": m.key,
            "definition": m.description,
            "breakdown": DIMENSIONS[self.breakdown].label if self.breakdown else None,
            "filters": [f.describe() for f in self.filters],
            "date_from": self.date_from.isoformat(),
            "date_to": self.date_to.isoformat(),
            "granularity": self.granularity,
            "compare_from": self.compare_from.isoformat() if self.compare_from else None,
            "compare_to": self.compare_to.isoformat() if self.compare_to else None,
        }

class Point(BaseModel):
    bucket: str
    value: float | None
    numerator: float
    denominator: float | None

class Total(BaseModel):
    value: float | None
    numerator: float
    denominator: float | None

class Series(BaseModel):
    key: str
    label: str
    total: Total
    compare_total: Total | None = None
    points: list[Point] = Field(default_factory=list)
    compare_points: list[Point] = Field(default_factory=list)

class MetricInfo(BaseModel):
    key: str
    label: str
    description: str
    format: MetricFormat
    higher_is_better: bool
    is_proportion: bool

class MetricQueryResult(BaseModel):
    metric: MetricInfo
    interpretation: dict[str, Any]
    series: list[Series]

def metric_info(m: Metric) -> MetricInfo:
    return MetricInfo(
        key=m.key,
        label=m.label,
        description=m.description,
        format=m.format,
        higher_is_better=m.higher_is_better,
        is_proportion=m.is_proportion,
    )

def bucket_expr(granularity: Granularity, ts_col: str) -> str:
    if granularity == "hour":
        return f"toStartOfHour({ts_col})"
    if granularity == "week":
        return f"toStartOfWeek(toDate({ts_col}), 1)"
    return f"toDate({ts_col})"

class _Compiled(BaseModel):
    sql: str
    params: dict[str, Any]

def _session_source(q: MetricQuery, params: dict[str, Any], breakdown_event_dim: str | None) -> str:
    """Per-session rollup subquery honouring filters of both scopes."""
    where = session_where(q.filters, params)
    fields = SESSION_ROLLUP_FIELDS
    if breakdown_event_dim:
        col = DIMENSIONS[breakdown_event_dim].col
        empty = "0" if DIMENSIONS[breakdown_event_dim].ch_type == "UInt32" else "''"
        fields += f",\n    groupUniqArrayIf({col}, {col} != {empty}) AS dims"
    return f"(SELECT {fields} FROM events WHERE {where} GROUP BY session_id)"

def compile_metric_query(
    q: MetricQuery,
    *,
    date_from: date,
    date_to: date,
    with_buckets: bool,
    restrict_dims: list[Any] | None = None,
    limit: int | None = None,
) -> _Compiled:
    m = get_metric(q.metric)
    params: dict[str, Any] = {"d_from": date_from, "d_to": date_to}
    breakdown = DIMENSIONS[q.breakdown] if q.breakdown else None

    if m.scope == Scope.session:
        event_dim_breakdown = breakdown.key if breakdown and breakdown.scope == Scope.event else None
        source = _session_source(q, params, event_dim_breakdown)
        ts_col = "session_ts"
        dim_expr = "dim" if event_dim_breakdown else (f"s_{breakdown.col}" if breakdown else "'all'")
        array_join = " ARRAY JOIN dims AS dim" if event_dim_breakdown else ""
        outer_where = "1"
    else:
        where = compile_filters(q.filters, prefix="f")
        params.update(where.params)
        source = "events"
        ts_col = "timestamp"
        dim_expr = breakdown.col if breakdown else "'all'"
        array_join = ""
        outer_where = f"{DATE_WINDOW} AND {where.sql}"
        if breakdown:
            empty = "0" if breakdown.ch_type == "UInt32" else "''"
            outer_where += f" AND {breakdown.col} != {empty}"

    if restrict_dims is not None and breakdown:
        params["dims"] = restrict_dims
        outer_where += f" AND {dim_expr} IN {{dims:Array({breakdown.ch_type})}}"

    bucket = bucket_expr(q.granularity or "day", ts_col) if with_buckets else "'total'"
    den = m.denominator or "NULL"
    order = "ORDER BY bucket, dim" if with_buckets else f"ORDER BY {m.denominator or m.numerator} DESC"
    limit_sql = f" LIMIT {int(limit)}" if limit else ""
    sql = f"""
SELECT {bucket} AS bucket, toString({dim_expr}) AS dim,
       {m.numerator} AS num, {den} AS den, {m.expression} AS value
FROM {source}{array_join}
WHERE {outer_where}
GROUP BY bucket, dim
{order}{limit_sql}
"""
    return _Compiled(sql=sql, params=params)

def _to_total(row: dict[str, Any] | None) -> Total:
    if row is None:
        return Total(value=None, numerator=0, denominator=None)
    return Total(value=_f(row["value"]), numerator=_f(row["num"]) or 0, denominator=_f(row["den"]))

def _to_point(row: dict[str, Any]) -> Point:
    b = row["bucket"]
    bucket = b.isoformat() if isinstance(b, datetime | date) else str(b)
    return Point(
        bucket=bucket,
        value=_f(row["value"]),
        numerator=_f(row["num"]) or 0,
        denominator=_f(row["den"]),
    )

def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def run_metric_query(q: MetricQuery) -> MetricQueryResult:
    m = get_metric(q.metric)
    label_for = _labeler(q.breakdown)

    totals = compile_metric_query(
        q,
        date_from=q.date_from,
        date_to=q.date_to,
        with_buckets=False,
        limit=q.limit if q.breakdown else None,
    )
    total_rows = run_query(totals.sql, totals.params, label=f"{m.key}:totals")
    keys = [r["dim"] for r in total_rows] or (["all"] if not q.breakdown else [])
    restrict = _typed_dims(q.breakdown, keys) if q.breakdown else None

    series: dict[str, Series] = {
        r["dim"]: Series(key=r["dim"], label=label_for(r["dim"]), total=_to_total(r)) for r in total_rows
    }
    if not q.breakdown and not series:
        series["all"] = Series(key="all", label=m.label, total=_to_total(None))

    if q.compare_from and q.compare_to:
        cmp = compile_metric_query(
            q,
            date_from=q.compare_from,
            date_to=q.compare_to,
            with_buckets=False,
            restrict_dims=restrict,
        )
        for r in run_query(cmp.sql, cmp.params, label=f"{m.key}:compare"):
            if r["dim"] in series:
                series[r["dim"]].compare_total = _to_total(r)
        for s in series.values():
            if s.compare_total is None:
                s.compare_total = _to_total(None)

    if q.granularity:
        trend = compile_metric_query(
            q, date_from=q.date_from, date_to=q.date_to, with_buckets=True, restrict_dims=restrict
        )
        for r in run_query(trend.sql, trend.params, label=f"{m.key}:trend"):
            if r["dim"] in series:
                series[r["dim"]].points.append(_to_point(r))
        if q.compare_from and q.compare_to and not q.breakdown:
            ctrend = compile_metric_query(
                q, date_from=q.compare_from, date_to=q.compare_to, with_buckets=True
            )
            for r in run_query(ctrend.sql, ctrend.params, label=f"{m.key}:compare_trend"):
                if r["dim"] in series:
                    series[r["dim"]].compare_points.append(_to_point(r))

    return MetricQueryResult(metric=metric_info(m), interpretation=q.describe(), series=list(series.values()))

def _typed_dims(breakdown: str | None, keys: list[str]) -> list[Any]:
    if breakdown and DIMENSIONS[breakdown].ch_type == "UInt32":
        return [int(k) for k in keys]
    return keys

def _labeler(breakdown: str | None):
    if breakdown == "product_id":
        from probelens.analytics.catalog import product_labels

        labels = product_labels()
        return lambda k: labels.get(k, f"Product {k}")
    if breakdown == "app_version":
        return lambda k: k or "web (no version)"
    return lambda k: k or "(none)"
