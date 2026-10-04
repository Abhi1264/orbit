from clickhouse_connect.driver.client import Client

from probelens.analytics.funnel import FUNNEL_EVENTS, FUNNEL_WINDOW_SECONDS
from probelens.analytics.metrics import METRICS
from probelens.analytics.query import SESSION_DIM_COLS, SESSION_FLAGS, SESSION_ROLLUP_FIELDS
from probelens.analytics.sql import NOT_POST_PURCHASE, POST_PURCHASE_EVENTS

FUNNEL_STEPS = [
    "search",
    "product_view",
    "add_to_cart",
    "checkout_started",
    "payment_started",
    "order_completed",
]
FUNNEL_LABELS = [FUNNEL_EVENTS[e] for e in FUNNEL_STEPS]
RETENTION_DAYS = (1, 7, 14, 30)

_SESSION_KPIS = {
    "sessions": METRICS["sessions"].numerator,
    "active_users": METRICS["users"].numerator,
    "converted_sessions": METRICS["conversion"].numerator,
    "checkout_sessions": METRICS["checkout_conversion"].denominator,
    "bounced_sessions": METRICS["bounce_rate"].numerator,
}
_EVENT_KPIS = {
    "orders": METRICS["orders"].numerator,
    "revenue": METRICS["revenue"].numerator,
    "order_lines": METRICS["return_rate"].denominator,
    "returns_initiated": METRICS["return_rate"].numerator,
    "payment_attempts": METRICS["payment_success_rate"].denominator,
    "payment_successes": METRICS["payment_success_rate"].numerator,
}


def _cols(exprs: dict[str, str | None]) -> str:
    return ",\n        ".join(f"{expr} AS {name}" for name, expr in exprs.items())


def session_rollup(where: str = "1") -> str:
    # Filter events before rolling up, as Orbit does; filtering whole sessions drifts at period edges.
    steps = ", ".join(f"event_name = '{e}'" for e in FUNNEL_STEPS)
    return f"""
SELECT
    session_id,
    user_id,
    toDate(session_ts) AS day,
    session_ts AS started_at,
    {", ".join(f"s_{c} AS {c}" for c in SESSION_DIM_COLS)},
    event_count,
    {", ".join(SESSION_FLAGS)},
    funnel_step,
    revenue
FROM (
    SELECT {SESSION_ROLLUP_FIELDS},
        windowFunnel({FUNNEL_WINDOW_SECONDS})(timestamp, {steps}) AS funnel_step,
        {METRICS["revenue"].numerator} AS revenue
    FROM events
    WHERE {NOT_POST_PURCHASE} AND {where}
    GROUP BY session_id
)"""


_RETENTION_COLS = ",\n    ".join(
    f"p.signup_date + {n} <= bounds.last_day AS d{n}_eligible, "
    f"has(a.active_days, p.signup_date + {n}) AS d{n}_retained"
    for n in RETENTION_DAYS
)

VIEWS: dict[str, str] = {
    # Date-filtered cards use session_rollup instead, to match Orbit at period edges.
    "bi_sessions": session_rollup(),
    "bi_daily_kpis": f"""
SELECT day, {", ".join(_SESSION_KPIS)}, {", ".join(_EVENT_KPIS)}
FROM (
    SELECT day,
        {_cols(_SESSION_KPIS)}
    FROM bi_sessions
    GROUP BY day
) AS s
FULL OUTER JOIN (
    SELECT event_date AS day,
        {_cols(_EVENT_KPIS)}
    FROM events
    GROUP BY day
) AS e USING (day)""",
    "bi_active_users": f"""
SELECT
    day,
    finalizeAggregation(users) AS dau,
    uniqMerge(users) OVER (ORDER BY day RANGE BETWEEN 6 PRECEDING AND CURRENT ROW) AS wau,
    uniqMerge(users) OVER (ORDER BY day RANGE BETWEEN 29 PRECEDING AND CURRENT ROW) AS mau
FROM (
    SELECT event_date AS day, uniqState(user_id) AS users
    FROM events
    WHERE {NOT_POST_PURCHASE}
    GROUP BY day
)""",
    "bi_retention": f"""
SELECT
    p.user_id AS user_id,
    p.signup_date AS signup_date,
    toStartOfWeek(p.signup_date, 1) AS signup_week,
    p.acquisition_source AS acquisition_channel,
    p.primary_platform AS platform,
    p.city_tier AS city_tier,
    {_RETENTION_COLS}
FROM user_profiles AS p
CROSS JOIN (
    SELECT min(event_date) AS first_day, max(event_date) AS last_day FROM events WHERE {NOT_POST_PURCHASE}
) AS bounds
LEFT JOIN (
    SELECT user_id, groupUniqArray(event_date) AS active_days
    FROM events
    WHERE {NOT_POST_PURCHASE}
    GROUP BY user_id
) AS a ON a.user_id = p.user_id
WHERE p.signup_date >= bounds.first_day""",
    "bi_order_lines": f"""
SELECT
    o.event_date AS day,
    o.timestamp AS ordered_at,
    o.order_id AS order_id,
    o.user_id AS user_id,
    o.product_id AS product_id,
    o.category AS category,
    o.subcategory AS subcategory,
    o.order_value AS line_value,
    o.payment_method AS payment_method,
    o.platform AS platform,
    o.traffic_source AS traffic_source,
    o.city_tier AS city_tier,
    o.user_type AS user_type,
    o.delivery_days AS delivery_days,
    pp.delivered AS delivered,
    pp.returned AS returned,
    pp.return_reason AS return_reason
FROM events AS o
LEFT JOIN (
    SELECT order_id, product_id,
        max(event_name = 'delivery_completed') AS delivered,
        max(event_name = 'return_initiated') AS returned,
        anyIf(return_reason, event_name = 'return_initiated') AS return_reason
    FROM events
    WHERE event_name IN {POST_PURCHASE_EVENTS}
    GROUP BY order_id, product_id
) AS pp ON pp.order_id = o.order_id AND pp.product_id = o.product_id
WHERE o.event_name = 'order_completed'""",
    "bi_returns": """
SELECT
    r.event_date AS day,
    r.timestamp AS returned_at,
    r.order_id AS order_id,
    r.product_id AS product_id,
    r.category AS category,
    r.subcategory AS subcategory,
    r.order_value AS item_value,
    r.return_reason AS return_reason,
    r.payment_method AS payment_method,
    r.platform AS platform,
    r.city_tier AS city_tier,
    c.order_id != 0 AS completed
FROM events AS r
LEFT JOIN (
    SELECT DISTINCT order_id, product_id FROM events WHERE event_name = 'return_completed'
) AS c ON c.order_id = r.order_id AND c.product_id = r.product_id
WHERE r.event_name = 'return_initiated'""",
    "bi_acquisition": """
SELECT day, channel AS traffic_source, sessions, new_customer_sessions, converted_sessions, revenue, signups
FROM (
    SELECT day, traffic_source AS channel,
        count() AS sessions,
        countIf(user_type = 'new') AS new_customer_sessions,
        countIf(has_order) AS converted_sessions,
        sum(revenue) AS revenue
    FROM bi_sessions
    GROUP BY day, channel
) AS s
FULL OUTER JOIN (
    SELECT signup_date AS day, acquisition_source AS channel, count() AS signups
    FROM user_profiles
    WHERE signup_date >= (SELECT min(event_date) FROM events)
    GROUP BY day, channel
) AS n USING (day, channel)""",
}


def apply_views(client: Client) -> list[str]:
    for name, sql in VIEWS.items():
        client.command(f"CREATE OR REPLACE VIEW {name} AS {sql}")
    return list(VIEWS)
