from datetime import date

from fastapi import APIRouter, Depends, Query

from probelens.analytics.cohort import CohortQuery, CohortResult, run_cohort
from probelens.analytics.funnel import FunnelQuery, FunnelResult, run_funnel
from probelens.analytics.meta import AnalyticsMeta, get_meta
from probelens.analytics.overview import InventoryRiskResult, OverviewKpis, inventory_risk, overview_kpis
from probelens.analytics.query import MetricQuery, MetricQueryResult, run_metric_query
from probelens.api.deps import DbSession, require
from probelens.core.permissions import Permission

router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(require(Permission.run_analytics))],
)

@router.get("/meta", response_model=AnalyticsMeta)
def meta() -> AnalyticsMeta:
    return get_meta()

@router.get("/overview", response_model=OverviewKpis)
def overview(
    date_from: date,
    date_to: date,
    compare_from: date | None = None,
    compare_to: date | None = None,
) -> OverviewKpis:
    return overview_kpis(date_from, date_to, compare_from, compare_to)

@router.get("/inventory-risk", response_model=InventoryRiskResult)
def inventory(
    db: DbSession, as_of: date, threshold_days: float = Query(default=7.0, ge=1, le=60)
) -> InventoryRiskResult:
    return inventory_risk(db, as_of, threshold_days)

@router.post("/query", response_model=MetricQueryResult)
def query(q: MetricQuery) -> MetricQueryResult:
    return run_metric_query(q)

@router.post("/funnel", response_model=FunnelResult)
def funnel(q: FunnelQuery) -> FunnelResult:
    return run_funnel(q)

@router.post("/cohort", response_model=CohortResult)
def cohort(q: CohortQuery) -> CohortResult:
    return run_cohort(q)
