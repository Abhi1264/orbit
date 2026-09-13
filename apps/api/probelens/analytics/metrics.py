"""Metric catalog.

Session-scoped metrics are computed over a per-session rollup (one row per
session with boolean step flags) so that "sessions with A and B" style
definitions are exact. Event-scoped metrics aggregate event rows directly.
"""

from dataclasses import dataclass
from enum import StrEnum

from probelens.analytics.dimensions import Scope

class MetricFormat(StrEnum):
    count = "count"
    currency = "currency"
    percent = "percent"
    ratio = "ratio"
    number = "number"
    days = "days"

@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    description: str
    format: MetricFormat
    scope: Scope
    numerator: str
    denominator: str | None = None
    higher_is_better: bool = True
    # Rate metrics are analysed as proportions (two-proportion tests etc.).
    is_proportion: bool = False

    @property
    def expression(self) -> str:
        if self.denominator is None:
            return self.numerator
        return f"if({self.denominator} = 0, NULL, {self.numerator} / {self.denominator})"

# Rollup columns available to session-scoped metrics (see query.SESSION_ROLLUP).
_S = Scope.session
_E = Scope.event

METRICS: dict[str, Metric] = {
    m.key: m
    for m in [
        Metric(
            "users",
            "Active users",
            "Distinct users with at least one session.",
            MetricFormat.count,
            _S,
            "uniq(user_id)",
        ),
        Metric("sessions", "Sessions", "Distinct sessions.", MetricFormat.count, _S, "count()"),
        Metric(
            "conversion",
            "Conversion rate",
            "Sessions with a completed order ÷ all sessions.",
            MetricFormat.percent,
            _S,
            "countIf(has_order)",
            "count()",
            is_proportion=True,
        ),
        Metric(
            "checkout_conversion",
            "Checkout conversion",
            "Sessions with a completed order ÷ sessions that started checkout.",
            MetricFormat.percent,
            _S,
            "countIf(has_order)",
            "countIf(has_checkout)",
            is_proportion=True,
        ),
        Metric(
            "add_to_cart_rate",
            "Add-to-cart rate",
            "Sessions with an add-to-cart ÷ sessions with a product view.",
            MetricFormat.percent,
            _S,
            "countIf(has_atc)",
            "countIf(has_pv)",
            is_proportion=True,
        ),
        Metric(
            "search_to_product_view_rate",
            "Search → product view",
            "Sessions that searched and then viewed a product ÷ sessions that searched.",
            MetricFormat.percent,
            _S,
            "countIf(has_search AND has_pv)",
            "countIf(has_search)",
            is_proportion=True,
        ),
        Metric(
            "bounce_rate",
            "Bounce rate",
            "Single-event sessions ÷ all sessions.",
            MetricFormat.percent,
            _S,
            "countIf(event_count = 1)",
            "count()",
            higher_is_better=False,
            is_proportion=True,
        ),
        Metric(
            "orders",
            "Orders",
            "Distinct completed orders.",
            MetricFormat.count,
            _E,
            "uniqIf(order_id, event_name = 'order_completed')",
        ),
        Metric(
            "revenue",
            "Revenue",
            "Sum of completed order line values.",
            MetricFormat.currency,
            _E,
            "sumIf(order_value, event_name = 'order_completed')",
        ),
        Metric(
            "aov",
            "Average order value",
            "Revenue ÷ distinct orders.",
            MetricFormat.currency,
            _E,
            "sumIf(order_value, event_name = 'order_completed')",
            "uniqIf(order_id, event_name = 'order_completed')",
        ),
        Metric(
            "return_rate",
            "Return rate",
            "Return-initiated order lines ÷ completed order lines in the period "
            "(returns lag orders by 3–14 days).",
            MetricFormat.percent,
            _E,
            "countIf(event_name = 'return_initiated')",
            "countIf(event_name = 'order_completed')",
            higher_is_better=False,
            is_proportion=True,
        ),
        Metric(
            "payment_success_rate",
            "Payment success rate",
            "Successful payments ÷ payment attempts.",
            MetricFormat.percent,
            _E,
            "countIf(event_name = 'payment_success')",
            "countIf(event_name = 'payment_started')",
            is_proportion=True,
        ),
        Metric(
            "payment_failure_rate",
            "Payment failure rate",
            "Failed payment attempts ÷ payment attempts.",
            MetricFormat.percent,
            _E,
            "countIf(event_name = 'payment_failed')",
            "countIf(event_name = 'payment_started')",
            higher_is_better=False,
            is_proportion=True,
        ),
        Metric(
            "payment_attempts",
            "Payment attempts",
            "payment_started events.",
            MetricFormat.count,
            _E,
            "countIf(event_name = 'payment_started')",
        ),
        Metric(
            "payment_failures",
            "Payment failures",
            "payment_failed events.",
            MetricFormat.count,
            _E,
            "countIf(event_name = 'payment_failed')",
            higher_is_better=False,
        ),
        Metric(
            "product_views",
            "Product views",
            "product_view events.",
            MetricFormat.count,
            _E,
            "countIf(event_name = 'product_view')",
        ),
        Metric(
            "searches",
            "Searches",
            "search events.",
            MetricFormat.count,
            _E,
            "countIf(event_name = 'search')",
        ),
        Metric(
            "returns",
            "Returns",
            "return_initiated events.",
            MetricFormat.count,
            _E,
            "countIf(event_name = 'return_initiated')",
            higher_is_better=False,
        ),
        Metric(
            "avg_delivery_days",
            "Avg delivery days",
            "Mean days from order to delivery for delivered lines.",
            MetricFormat.days,
            _E,
            "sumIf(delivery_days, event_name = 'delivery_completed')",
            "countIf(event_name = 'delivery_completed')",
            higher_is_better=False,
        ),
    ]
}

OVERVIEW_METRICS = ["revenue", "orders", "conversion", "aov", "return_rate", "users"]

def get_metric(key: str) -> Metric:
    try:
        return METRICS[key]
    except KeyError as exc:
        raise ValueError(f"Unknown metric '{key}'") from exc

def format_value(fmt: MetricFormat | str, v: float | None) -> str:
    """Human-readable metric value for generated prose (findings, memos, AI answers)."""
    if v is None:
        return "n/a"
    f = fmt.value if isinstance(fmt, MetricFormat) else fmt
    if f == "percent":
        return f"{v * 100:.1f}%"
    if f == "currency":
        return f"₹{v:,.0f}"
    if f == "days":
        return f"{v:.1f} days"
    if f == "ratio":
        return f"{v:.2f}"
    return f"{v:,.0f}"
