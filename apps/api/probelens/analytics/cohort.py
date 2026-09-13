"""Weekly cohort matrices computed from user_profiles joined to events."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from probelens.db.clickhouse import run_query

CohortType = Literal["signup", "first_purchase"]
Measure = Literal["retention", "repeat_purchase", "revenue_per_user"]

# Cohort filters apply to user attributes, so they map onto user_profiles columns.
COHORT_FILTER_COLUMNS = {
    "platform": "primary_platform",
    "traffic_source": "acquisition_source",
    "city_tier": "city_tier",
    "country": "country",
    "payment_method": "preferred_payment",
}

MEASURE_LABELS = {
    "retention": "Users with a session in week k ÷ cohort size",
    "repeat_purchase": (
        "Users with an order in week k ÷ cohort size "
        "(excluding the cohort-defining order for first-purchase cohorts)"
    ),
    "revenue_per_user": "Revenue in week k ÷ cohort size",
}

class CohortFilter(BaseModel):
    dimension: str
    value: str

    @model_validator(mode="after")
    def _check(self) -> "CohortFilter":
        if self.dimension not in COHORT_FILTER_COLUMNS:
            raise ValueError(f"Cohort filters support {sorted(COHORT_FILTER_COLUMNS)}")
        return self

class CohortQuery(BaseModel):
    cohort_type: CohortType = "signup"
    measure: Measure = "retention"
    date_from: date
    date_to: date
    weeks: int = Field(default=8, ge=2, le=16)
    filters: list[CohortFilter] = Field(default_factory=list)

class CohortRow(BaseModel):
    cohort: str
    size: int
    values: list[float | None]  # index k = weeks since cohort date

class CohortResult(BaseModel):
    cohort_type: CohortType
    measure: Measure
    measure_definition: str
    weeks: int
    rows: list[CohortRow]
    interpretation: dict[str, Any]

def run_cohort(q: CohortQuery) -> CohortResult:
    cohort_col = "signup_date" if q.cohort_type == "signup" else "first_purchase_date"
    params: dict[str, Any] = {"d_from": q.date_from, "d_to": q.date_to, "weeks": q.weeks}
    clauses = [f"{cohort_col} BETWEEN {{d_from:Date}} AND {{d_to:Date}}"]
    if q.cohort_type == "first_purchase":
        clauses.append("first_purchase_date > toDate('1970-01-01')")
    for i, f in enumerate(q.filters):
        params[f"c{i}"] = f.value
        clauses.append(f"{COHORT_FILTER_COLUMNS[f.dimension]} = {{c{i}:String}}")
    profiles = (
        f"(SELECT user_id, {cohort_col} AS cohort_date FROM user_profiles WHERE {' AND '.join(clauses)})"
    )

    if q.measure == "retention":
        event_where = "1"
        agg = "uniq(user_id)"
    elif q.measure == "repeat_purchase":
        event_where = "event_name = 'order_completed'"
        agg = "uniq(user_id)"
    else:
        event_where = "event_name = 'order_completed'"
        agg = "sum(order_value)"

    # For first-purchase cohorts the defining order sits in week 0; exclude that day so
    # week 0 does not trivially read 100% for repeat purchase / revenue.
    exclude_day = (
        " AND e.event_date > p.cohort_date"
        if q.cohort_type == "first_purchase" and q.measure != "retention"
        else ""
    )

    sizes_sql = (
        f"SELECT toStartOfWeek(cohort_date, 1) AS cohort, uniq(user_id) AS size FROM {profiles} "
        "GROUP BY cohort ORDER BY cohort"
    )
    values_sql = f"""
SELECT toStartOfWeek(p.cohort_date, 1) AS cohort,
       intDiv(dateDiff('day', p.cohort_date, e.event_date), 7) AS k,
       {agg} AS v
FROM (SELECT user_id, event_date, event_name, order_value FROM events
      WHERE event_date >= {{d_from:Date}} AND {event_where}) AS e
INNER JOIN {profiles} AS p ON e.user_id = p.user_id
WHERE e.event_date >= p.cohort_date{exclude_day} AND k < {{weeks:UInt32}}
GROUP BY cohort, k
"""
    sizes = run_query(sizes_sql, params, label="cohort:sizes")
    values = run_query(values_sql, params, label="cohort:values")

    by_cohort: dict[str, dict[int, float]] = {}
    for r in values:
        by_cohort.setdefault(str(r["cohort"]), {})[int(r["k"])] = float(r["v"])

    rows: list[CohortRow] = []
    max_k_for = lambda cohort: (q.date_to - date.fromisoformat(cohort)).days // 7  # noqa: E731
    for s in sizes:
        cohort = str(s["cohort"])
        size = int(s["size"])
        vals = by_cohort.get(cohort, {})
        reachable = max_k_for(cohort)
        row_values: list[float | None] = []
        for k in range(q.weeks):
            if k > reachable or size == 0:
                row_values.append(None)
            else:
                row_values.append(vals.get(k, 0.0) / size)
        rows.append(CohortRow(cohort=cohort, size=size, values=row_values))

    return CohortResult(
        cohort_type=q.cohort_type,
        measure=q.measure,
        measure_definition=MEASURE_LABELS[q.measure],
        weeks=q.weeks,
        rows=rows,
        interpretation={
            "cohort": "signup week" if q.cohort_type == "signup" else "first purchase week",
            "measure": q.measure,
            "filters": [f"{f.dimension} = {f.value}" for f in q.filters],
            "date_from": q.date_from.isoformat(),
            "date_to": q.date_to.isoformat(),
        },
    )
