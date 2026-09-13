from datetime import date

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from probelens.analytics.metrics import OVERVIEW_METRICS, get_metric
from probelens.analytics.query import MetricInfo, MetricQuery, Point, Total, metric_info, run_metric_query
from probelens.db.clickhouse import run_query
from probelens.models import Product


class Kpi(BaseModel):
    metric: MetricInfo
    current: Total
    previous: Total | None
    points: list[Point]
    compare_points: list[Point]


class OverviewKpis(BaseModel):
    date_from: date
    date_to: date
    compare_from: date | None
    compare_to: date | None
    kpis: list[Kpi]


def overview_kpis(
    date_from: date, date_to: date, compare_from: date | None, compare_to: date | None
) -> OverviewKpis:
    granularity = "week" if (date_to - date_from).days > 60 else "day"
    kpis: list[Kpi] = []
    for key in OVERVIEW_METRICS:
        result = run_metric_query(
            MetricQuery(
                metric=key,
                date_from=date_from,
                date_to=date_to,
                granularity=granularity,
                compare_from=compare_from,
                compare_to=compare_to,
            )
        )
        s = result.series[0]
        kpis.append(
            Kpi(
                metric=metric_info(get_metric(key)),
                current=s.total,
                previous=s.compare_total,
                points=s.points,
                compare_points=s.compare_points,
            )
        )
    return OverviewKpis(
        date_from=date_from, date_to=date_to, compare_from=compare_from, compare_to=compare_to, kpis=kpis
    )


class InventoryRisk(BaseModel):
    product_id: int
    sku: str
    name: str
    category: str
    stock_units: int
    units_sold_14d: int
    daily_velocity: float
    days_of_cover: float | None
    revenue_14d: float


class InventoryRiskResult(BaseModel):
    as_of: date
    threshold_days: float
    items: list[InventoryRisk]


def inventory_risk(
    db: Session, as_of: date, threshold_days: float = 7.0, limit: int = 25
) -> InventoryRiskResult:
    """Products whose current stock covers fewer than `threshold_days` of trailing
    14-day sales velocity. Velocity comes from ClickHouse, stock from Postgres."""
    rows = run_query(
        """
SELECT product_id, count() AS units, sum(order_value) AS revenue
FROM events
WHERE event_name = 'order_completed' AND event_date BETWEEN {d_from:Date} AND {d_to:Date}
GROUP BY product_id
""",
        {"d_from": as_of.fromordinal(as_of.toordinal() - 13), "d_to": as_of},
        label="inventory:velocity",
    )
    velocity = {int(r["product_id"]): (int(r["units"]), float(r["revenue"])) for r in rows}
    if not velocity:
        return InventoryRiskResult(as_of=as_of, threshold_days=threshold_days, items=[])
    products = db.scalars(select(Product).where(Product.id.in_(list(velocity)), Product.is_active)).all()
    items: list[InventoryRisk] = []
    for p in products:
        units, revenue = velocity[p.id]
        daily = units / 14
        cover = p.stock_units / daily if daily > 0 else None
        if cover is not None and cover < threshold_days:
            items.append(
                InventoryRisk(
                    product_id=p.id,
                    sku=p.sku,
                    name=p.name,
                    category=p.category,
                    stock_units=p.stock_units,
                    units_sold_14d=units,
                    daily_velocity=round(daily, 2),
                    days_of_cover=round(cover, 1),
                    revenue_14d=round(revenue, 2),
                )
            )
    items.sort(key=lambda i: (i.days_of_cover or 0, -i.revenue_14d))
    return InventoryRiskResult(as_of=as_of, threshold_days=threshold_days, items=items[:limit])
