from datetime import date

from pydantic import BaseModel

from probelens.analytics.dimensions import DIMENSIONS, Dimension, Scope
from probelens.analytics.funnel import FUNNEL_EVENTS
from probelens.analytics.metrics import METRICS
from probelens.analytics.query import MetricInfo, metric_info
from probelens.db.clickhouse import run_query

# Dimensions whose distinct values are small enough to offer as dropdowns.
ENUMERABLE = [
    "platform",
    "device_type",
    "app_version",
    "country",
    "city",
    "city_tier",
    "traffic_source",
    "user_type",
    "category",
    "subcategory",
    "payment_method",
    "payment_gateway",
    "failure_reason",
    "return_reason",
    "search_query",
]


class DimensionInfo(BaseModel):
    key: str
    label: str
    scope: Scope
    values: list[str]


class AnalyticsMeta(BaseModel):
    data_start: date | None
    data_end: date | None
    total_events: int
    metrics: list[MetricInfo]
    dimensions: list[DimensionInfo]
    funnel_events: dict[str, str]


def _dimension_values() -> dict[str, list[str]]:
    selects = ", ".join(f"groupUniqArrayIf(toString({d}), {d} != '') AS {d}" for d in ENUMERABLE)
    rows = run_query(f"SELECT {selects} FROM events", label="meta:dimension_values")
    if not rows:
        return {d: [] for d in ENUMERABLE}
    return {d: sorted(rows[0][d])[:200] for d in ENUMERABLE}


def get_meta() -> AnalyticsMeta:
    rows = run_query(
        "SELECT min(event_date) AS s, max(event_date) AS e, count() AS n FROM events",
        label="meta:range",
    )
    row = rows[0] if rows else {"s": None, "e": None, "n": 0}
    values = _dimension_values()
    start = row["s"] if row["n"] else None
    end = row["e"] if row["n"] else None
    return AnalyticsMeta(
        data_start=_as_date(start),
        data_end=_as_date(end),
        total_events=int(row["n"]),
        metrics=[metric_info(m) for m in METRICS.values()],
        dimensions=[_dim_info(d, values.get(d.key, [])) for d in DIMENSIONS.values()],
        funnel_events=FUNNEL_EVENTS,
    )


def _dim_info(d: Dimension, values: list[str]) -> DimensionInfo:
    return DimensionInfo(key=d.key, label=d.label, scope=d.scope, values=values)


def _as_date(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])
