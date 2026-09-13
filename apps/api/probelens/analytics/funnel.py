"""Ordered session funnels via ClickHouse windowFunnel."""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, model_validator

from probelens.analytics.dimensions import DIMENSIONS, Filter, Scope
from probelens.analytics.sql import session_where
from probelens.db.clickhouse import run_query

FUNNEL_EVENTS: dict[str, str] = {
    "home_view": "Home",
    "search": "Search",
    "search_result_view": "Search results",
    "product_view": "Product view",
    "add_to_wishlist": "Wishlist",
    "add_to_cart": "Add to cart",
    "checkout_started": "Checkout",
    "payment_started": "Payment",
    "payment_success": "Payment success",
    "order_completed": "Purchase",
}

DEFAULT_FUNNEL = [
    "home_view",
    "product_view",
    "add_to_cart",
    "checkout_started",
    "payment_started",
    "order_completed",
]

FUNNEL_WINDOW_SECONDS = 24 * 3600

class FunnelSegment(BaseModel):
    label: str = "All sessions"
    filters: list[Filter] = Field(default_factory=list)

class FunnelQuery(BaseModel):
    steps: list[str] = Field(default_factory=lambda: list(DEFAULT_FUNNEL), min_length=2, max_length=8)
    date_from: date
    date_to: date
    segments: list[FunnelSegment] = Field(
        default_factory=lambda: [FunnelSegment()], min_length=1, max_length=4
    )
    breakdown: str | None = None
    limit: int = Field(default=6, ge=1, le=20)

    @model_validator(mode="after")
    def _check(self) -> "FunnelQuery":
        unknown = [s for s in self.steps if s not in FUNNEL_EVENTS]
        if unknown:
            raise ValueError(f"Unknown funnel steps: {unknown}")
        if self.breakdown and (
            self.breakdown not in DIMENSIONS or DIMENSIONS[self.breakdown].scope != Scope.session
        ):
            raise ValueError("Funnel breakdown must be a session-level dimension")
        if self.breakdown and len(self.segments) > 1:
            raise ValueError("Use either a breakdown or multiple segments, not both")
        return self

class FunnelStep(BaseModel):
    event: str
    label: str
    sessions: int
    users: int
    step_conversion: float | None  # from previous step
    overall_conversion: float | None  # from first step
    drop_off: int

class FunnelSeries(BaseModel):
    key: str
    label: str
    filters: list[str]
    total_sessions: int
    steps: list[FunnelStep]

class FunnelResult(BaseModel):
    steps: list[str]
    window_seconds: int
    series: list[FunnelSeries]
    interpretation: dict[str, Any]

def _compile(
    q: FunnelQuery, filters: list[Filter], breakdown: str | None, limit: int
) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {"d_from": q.date_from, "d_to": q.date_to}
    where = session_where(filters, params)

    conds = ", ".join(f"event_name = {{step{i}:String}}" for i in range(len(q.steps)))
    for i, s in enumerate(q.steps):
        params[f"step{i}"] = s
    dim = f"any({DIMENSIONS[breakdown].col})" if breakdown else "'all'"
    step_cols = ",\n  ".join(
        f"countIf(level >= {i + 1}) AS s{i}, uniqIf(user_id, level >= {i + 1}) AS u{i}"
        for i in range(len(q.steps))
    )
    sql = f"""
SELECT toString(dim) AS dim, count() AS sessions,
  {step_cols}
FROM (
  SELECT session_id, any(user_id) AS user_id, {dim} AS dim,
         windowFunnel({FUNNEL_WINDOW_SECONDS})(timestamp, {conds}) AS level
  FROM events
  WHERE {where}
  GROUP BY session_id
)
GROUP BY dim
ORDER BY sessions DESC
LIMIT {int(limit)}
"""
    return sql, params

def _to_steps(q: FunnelQuery, row: dict[str, Any]) -> list[FunnelStep]:
    steps: list[FunnelStep] = []
    first = int(row["s0"]) if row else 0
    prev = None
    for i, ev in enumerate(q.steps):
        sessions = int(row[f"s{i}"])
        users = int(row[f"u{i}"])
        steps.append(
            FunnelStep(
                event=ev,
                label=FUNNEL_EVENTS[ev],
                sessions=sessions,
                users=users,
                step_conversion=(sessions / prev) if prev else None,
                overall_conversion=(sessions / first)
                if first and i > 0
                else (1.0 if i == 0 and first else None),
                drop_off=(prev - sessions) if prev is not None else 0,
            )
        )
        prev = sessions
    return steps

def run_funnel(q: FunnelQuery) -> FunnelResult:
    series: list[FunnelSeries] = []
    if q.breakdown:
        sql, params = _compile(q, q.segments[0].filters, q.breakdown, q.limit)
        rows = run_query(sql, params, label="funnel:breakdown")
        for r in rows:
            series.append(
                FunnelSeries(
                    key=r["dim"],
                    label=r["dim"] or "(none)",
                    filters=[f.describe() for f in q.segments[0].filters],
                    total_sessions=int(r["sessions"]),
                    steps=_to_steps(q, r),
                )
            )
    else:
        for i, seg in enumerate(q.segments):
            sql, params = _compile(q, seg.filters, None, 1)
            rows = run_query(sql, params, label="funnel:segment")
            row = (
                rows[0]
                if rows
                else {
                    **{f"s{i}": 0 for i in range(len(q.steps))},
                    **{f"u{i}": 0 for i in range(len(q.steps))},
                    "sessions": 0,
                }
            )
            series.append(
                FunnelSeries(
                    key=f"segment_{i}",
                    label=seg.label,
                    filters=[f.describe() for f in seg.filters],
                    total_sessions=int(row["sessions"]),
                    steps=_to_steps(q, row),
                )
            )
    return FunnelResult(
        steps=q.steps,
        window_seconds=FUNNEL_WINDOW_SECONDS,
        series=series,
        interpretation={
            "steps": [FUNNEL_EVENTS[s] for s in q.steps],
            "date_from": q.date_from.isoformat(),
            "date_to": q.date_to.isoformat(),
            "segments": [
                {"label": s.label, "filters": [f.describe() for f in s.filters]} for s in q.segments
            ],
            "breakdown": DIMENSIONS[q.breakdown].label if q.breakdown else None,
            "ordering": "Steps must occur in order within a session (24h window).",
        },
    )
