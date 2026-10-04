import json
from dataclasses import dataclass, field
from string import Template
from typing import Any, Literal

from probelens.analytics.metrics import METRICS
from probelens.bi.views import FUNNEL_LABELS, FUNNEL_STEPS, RETENTION_DAYS, session_rollup

Database = Literal["clickhouse", "postgres"]


@dataclass(frozen=True)
class Filter:
    slug: str
    name: str
    kind: Literal["date", "string"]


@dataclass(frozen=True)
class Card:
    name: str
    sql: str
    display: str
    width: int
    height: int
    # template tag -> (table, column) it filters
    fields: dict[str, tuple[str, str]]
    database: Database = "clickhouse"
    viz: dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass(frozen=True)
class Text:
    markdown: str
    width: int = 24
    height: int = 2


@dataclass(frozen=True)
class Dashboard:
    name: str
    description: str
    filters: list[Filter]
    rows: list[list[Card | Text]]

    @property
    def cards(self) -> list[Card]:
        return [c for row in self.rows for c in row if isinstance(c, Card)]


_SUBS = {key: metric.expression for key, metric in METRICS.items()} | {
    "steps": str(len(FUNNEL_STEPS)),
    "step_labels": "[" + ", ".join(f"'{label}'" for label in FUNNEL_LABELS) + "]",
    "step_counts": "["
    + ", ".join(f"countIf(funnel_step >= {i})" for i in range(1, len(FUNNEL_STEPS) + 1))
    + "]",
}


def _sql(text: str) -> str:
    return Template(text).substitute(_SUBS).strip()


def _col_key(name: str) -> str:
    return json.dumps(["name", name], separators=(",", ":"))


def _columns(style: dict[str, Any], *names: str) -> dict[str, Any]:
    return {_col_key(n): dict(style) for n in names}


_PCT = {"number_style": "percent", "decimals": 1}
_INR = {
    "number_style": "currency",
    "currency": "INR",
    "currency_style": "symbol",
    "currency_in_header": False,
    "decimals": 0,
}

# Native query columns otherwise display under their SQL names.
_TITLES = {
    "aov": "Average order value",
    "conversion": "Conversion rate",
    "cumulative_users": "Exposed users",
    "d7_retention": "Day-7 retention",
    "p_value": "p-value",
    "search_to_order": "Search → order",
    "traffic_source": "Channel",
}


def title(column: str) -> str:
    if column in _TITLES:
        return _TITLES[column]
    text = column.replace("_", " ")
    return text[:1].upper() + text[1:]


def viz(
    pct: tuple[str, ...] = (),
    inr: tuple[str, ...] = (),
    titles: dict[str, str] | None = None,
    formats: dict[str, dict[str, Any]] | None = None,
    **settings: Any,
) -> dict[str, Any]:
    cols: dict[str, Any] = _columns(_PCT, *pct) | _columns(_INR, *inr)
    for name, fmt in (formats or {}).items():
        cols.setdefault(_col_key(name), {}).update(fmt)
    for name, text in (titles or {}).items():
        cols.setdefault(_col_key(name), {})["column_title"] = text
    out = {key.replace("__", "."): value for key, value in settings.items()}
    if cols:
        out["column_settings"] = cols
    return out


def graph(
    dims: list[str], metrics: list[str], series: dict[str, dict[str, Any]] | None = None, **settings: Any
) -> dict[str, Any]:
    series_settings = {m: {"title": title(m)} | (series or {}).get(m, {}) for m in metrics}
    defaults = {
        "graph.dimensions": dims,
        "graph.metrics": metrics,
        "graph.x_axis.title_text": title(dims[0]),
        "series_settings": series_settings,
    }
    if len(metrics) == 1:
        defaults["graph.y_axis.title_text"] = title(metrics[0])
    return defaults | viz(**settings)


def with_titles(settings: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    cols = dict(settings.get("column_settings", {}))
    for name in columns:
        key = _col_key(name)
        cols[key] = {"column_title": title(name)} | cols.get(key, {})
    return settings | {"column_settings": cols} if cols else settings


DATE = Filter("date", "Date", "date")
PLATFORM = Filter("platform", "Platform", "string")
CITY_TIER = Filter("city_tier", "City tier", "string")
CHANNEL = Filter("channel", "Acquisition channel", "string")
CATEGORY = Filter("category", "Category", "string")
PAYMENT = Filter("payment_method", "Payment method", "string")
SIGNUP = Filter("signup_date", "Signup date", "date")
EXPERIMENT = Filter("experiment", "Experiment", "string")

_EVENTS_DATE = {"date": ("events", "event_date")}
_SESSIONS = f"({session_rollup('{{date}}')})"


def _scalar(name: str, sql: str, fields: dict[str, tuple[str, str]], width: int = 4, **fmt: Any) -> Card:
    return Card(name, _sql(sql), "scalar", width, 3, fields, viz=viz(**fmt))


OVERVIEW = Dashboard(
    "Orbit · Product overview",
    "Headline product metrics with Orbit's definitions.",
    [DATE],
    [
        [
            Text(
                "**Product overview.** Same events and metric definitions as Orbit. Rates are "
                "computed over the whole selected period, not averaged across days. Active users "
                "are users with at least one session."
            )
        ],
        [
            _scalar("Orders", "SELECT ${orders} AS orders FROM events WHERE {{date}}", _EVENTS_DATE),
            _scalar(
                "Revenue",
                "SELECT ${revenue} AS revenue FROM events WHERE {{date}}",
                _EVENTS_DATE,
                inr=("revenue",),
            ),
            _scalar(
                "Conversion rate",
                f"SELECT ${{conversion}} AS conversion FROM {_SESSIONS}",
                _EVENTS_DATE,
                pct=("conversion",),
            ),
            _scalar(
                "Checkout conversion",
                f"SELECT ${{checkout_conversion}} AS checkout_conversion FROM {_SESSIONS}",
                _EVENTS_DATE,
                pct=("checkout_conversion",),
            ),
            _scalar(
                "Payment success rate",
                "SELECT ${payment_success_rate} AS payment_success_rate FROM events WHERE {{date}}",
                _EVENTS_DATE,
                pct=("payment_success_rate",),
            ),
            _scalar(
                "Return rate",
                "SELECT ${return_rate} AS return_rate FROM events WHERE {{date}}",
                _EVENTS_DATE,
                pct=("return_rate",),
            ),
        ],
        [
            _scalar("Active users", f"SELECT ${{users}} AS users FROM {_SESSIONS}", _EVENTS_DATE, width=8),
            _scalar("Sessions", f"SELECT ${{sessions}} AS sessions FROM {_SESSIONS}", _EVENTS_DATE, width=8),
            _scalar(
                "Average order value",
                "SELECT ${aov} AS aov FROM events WHERE {{date}}",
                _EVENTS_DATE,
                width=8,
                inr=("aov",),
            ),
        ],
        [
            Card(
                "Daily, weekly and monthly active users",
                "SELECT day, dau AS DAU, wau AS WAU, mau AS MAU\n"
                "FROM bi_active_users WHERE {{date}} ORDER BY day",
                "line",
                24,
                6,
                {"date": ("bi_active_users", "day")},
                viz=graph(
                    ["day"],
                    ["DAU", "WAU", "MAU"],
                    graph__x_axis__title_text="",
                    graph__y_axis__title_text="Users",
                ),
                description="WAU and MAU count distinct users over the trailing 7 and 30 days, so they "
                "ramp up over the first month of data.",
            )
        ],
        [
            Card(
                "Revenue and orders by day",
                "SELECT day, revenue, orders FROM bi_daily_kpis WHERE {{date}} ORDER BY day",
                "combo",
                12,
                6,
                {"date": ("bi_daily_kpis", "day")},
                viz=graph(
                    ["day"],
                    ["revenue", "orders"],
                    series={"revenue": {"display": "bar"}, "orders": {"display": "line", "axis": "right"}},
                    inr=("revenue",),
                    graph__x_axis__title_text="",
                ),
            ),
            Card(
                "Conversion by day",
                _sql(f"""
SELECT day, ${{conversion}} AS conversion, ${{checkout_conversion}} AS checkout_conversion
FROM {_SESSIONS}
GROUP BY day
ORDER BY day"""),
                "line",
                12,
                6,
                _EVENTS_DATE,
                viz=graph(
                    ["day"],
                    ["conversion", "checkout_conversion"],
                    pct=("conversion", "checkout_conversion"),
                    graph__x_axis__title_text="",
                ),
            ),
        ],
        [
            Card(
                "Payment success and return rate by week",
                """
SELECT toStartOfWeek(day, 1) AS week,
    if(sum(payment_attempts) = 0, NULL, sum(payment_successes) / sum(payment_attempts))
        AS payment_success_rate,
    if(sum(order_lines) = 0, NULL, sum(returns_initiated) / sum(order_lines)) AS return_rate
FROM bi_daily_kpis
WHERE {{date}}
GROUP BY week
ORDER BY week""".strip(),
                "line",
                12,
                6,
                {"date": ("bi_daily_kpis", "day")},
                viz=graph(
                    ["week"],
                    ["payment_success_rate", "return_rate"],
                    pct=("payment_success_rate", "return_rate"),
                    graph__x_axis__title_text="",
                ),
            ),
            Card(
                "Revenue by category",
                """
SELECT category, sum(line_value) AS revenue, uniq(order_id) AS orders
FROM bi_order_lines
WHERE {{date}}
GROUP BY category
ORDER BY revenue DESC""".strip(),
                "row",
                12,
                6,
                {"date": ("bi_order_lines", "day")},
                viz=graph(["category"], ["revenue"], inr=("revenue",)),
            ),
        ],
    ],
)


_FUNNEL_FIELDS = {
    "date": ("events", "event_date"),
    "platform": ("events", "platform"),
    "city_tier": ("events", "city_tier"),
    "channel": ("events", "traffic_source"),
    "category": ("events", "category"),
    "payment_method": ("events", "payment_method"),
}
# As in Orbit's session_where: event filters keep whole sessions with a matching event.
_FUNNEL_SESSIONS = "({})".format(
    session_rollup(
        "{{date}} AND {{platform}} AND {{city_tier}} AND {{channel}}\n"
        "        AND session_id IN (SELECT session_id FROM events WHERE {{date}} AND {{category}})\n"
        "        AND session_id IN (SELECT session_id FROM events WHERE {{date}} AND {{payment_method}})"
    )
)


def _conversion_by(dim: str, label: str) -> Card:
    return Card(
        f"Search-to-order conversion by {label}",
        _sql(f"""
SELECT {dim},
    if(countIf(funnel_step >= 1) = 0, NULL, countIf(funnel_step = ${{steps}}) / countIf(funnel_step >= 1))
        AS search_to_order
FROM {_FUNNEL_SESSIONS}
GROUP BY {dim}
ORDER BY search_to_order DESC"""),
        "bar",
        12,
        6,
        _FUNNEL_FIELDS,
        viz=graph([dim], ["search_to_order"], pct=("search_to_order",), graph__show_values=True),
    )


FUNNEL = Dashboard(
    "Orbit · Conversion funnel",
    "Search to order, with Orbit's 24-hour session funnel.",
    [DATE, PLATFORM, CITY_TIER, CHANNEL, CATEGORY, PAYMENT],
    [
        [
            Text(
                "**Conversion funnel.** Sessions that searched, viewed a product, added to cart, started "
                "checkout, started payment and completed an order, in that order within 24 hours (Orbit's "
                "funnel window). Category and payment method keep whole sessions that include a matching "
                "event, as in Orbit. Reproduce it in Orbit's Funnels page with the same steps.",
                height=3,
            )
        ],
        [
            Card(
                "Search → order funnel",
                _sql(f"""
SELECT step, sessions
FROM (SELECT ${{step_counts}} AS counts FROM {_FUNNEL_SESSIONS})
ARRAY JOIN ${{step_labels}} AS step, counts AS sessions"""),
                "funnel",
                24,
                7,
                _FUNNEL_FIELDS,
                viz={"funnel.dimension": "step", "funnel.metric": "sessions"},
            )
        ],
        [
            Card(
                "Step conversion",
                _sql(f"""
SELECT step, sessions,
    if(previous = 0, NULL, sessions / previous) AS step_conversion,
    if(counts[1] = 0, NULL, sessions / counts[1]) AS overall_conversion,
    previous - sessions AS drop_off
FROM (SELECT ${{step_counts}} AS counts FROM {_FUNNEL_SESSIONS})
ARRAY JOIN ${{step_labels}} AS step, counts AS sessions,
    arrayPushFront(arrayPopBack(counts), counts[1]) AS previous"""),
                "table",
                24,
                8,
                _FUNNEL_FIELDS,
                viz=viz(
                    pct=("step_conversion", "overall_conversion"),
                    titles={
                        "step_conversion": "From previous step",
                        "overall_conversion": "From search",
                        "drop_off": "Drop-off",
                    },
                ),
            ),
        ],
        [
            Card(
                "Funnel by platform",
                _sql(f"""
SELECT platform,
    {", ".join(f"countIf(funnel_step >= {i + 1}) AS {step}" for i, step in enumerate(FUNNEL_STEPS))},
    if(countIf(funnel_step >= 1) = 0, NULL, countIf(funnel_step = ${{steps}}) / countIf(funnel_step >= 1))
        AS search_to_order
FROM {_FUNNEL_SESSIONS}
GROUP BY platform
ORDER BY platform"""),
                "table",
                24,
                5,
                _FUNNEL_FIELDS,
                viz=viz(
                    pct=("search_to_order",),
                    titles=dict(zip(FUNNEL_STEPS, FUNNEL_LABELS, strict=True))
                    | {"search_to_order": "Search → order"},
                ),
            ),
        ],
        [_conversion_by("traffic_source", "acquisition channel"), _conversion_by("city_tier", "city tier")],
    ],
)


_RETENTION_FIELDS = {
    "signup_date": ("bi_retention", "signup_date"),
    "platform": ("bi_retention", "platform"),
    "channel": ("bi_retention", "acquisition_channel"),
    "city_tier": ("bi_retention", "city_tier"),
}
_RETENTION_WHERE = "WHERE {{signup_date}} AND {{platform}} AND {{channel}} AND {{city_tier}}"


def _rate(n: int) -> str:
    return f"if(countIf(d{n}_eligible) = 0, NULL, countIf(d{n}_retained) / countIf(d{n}_eligible))"


def _retention_by(dim: str, label: str) -> Card:
    return Card(
        f"Day-7 retention by {label}",
        f"SELECT {dim}, {_rate(7)} AS d7_retention, countIf(d7_eligible) AS customers\n"
        f"FROM bi_retention\n{_RETENTION_WHERE}\nGROUP BY {dim}\nORDER BY d7_retention DESC",
        "bar",
        12,
        6,
        _RETENTION_FIELDS,
        viz=graph([dim], ["d7_retention"], pct=("d7_retention",), graph__show_values=True),
    )


RETENTION = Dashboard(
    "Orbit · Retention",
    "Day 1 / 7 / 14 / 30 retention of new customers.",
    [SIGNUP, PLATFORM, CHANNEL, CITY_TIER],
    [
        [
            Text(
                "**Retention.** Day-N retention is the share of customers who signed up in the selected "
                "period and had a session exactly N days after signing up. Only customers whose day N is "
                "inside the data count toward that day's rate. Orbit's Cohorts page shows weekly retention "
                "of the same users.",
                height=3,
            )
        ],
        [
            Card(
                f"Day-{n} retention",
                f"SELECT {_rate(n)} AS d{n}_retention FROM bi_retention {_RETENTION_WHERE}",
                "scalar",
                6,
                3,
                _RETENTION_FIELDS,
                viz=viz(pct=(f"d{n}_retention",)),
            )
            for n in RETENTION_DAYS
        ],
        [
            Card(
                f"Retention curve, customers past day {max(RETENTION_DAYS)}",
                f"""
SELECT day, retention
FROM (
    SELECT [{", ".join(_rate(n) for n in RETENTION_DAYS)}] AS rates
    FROM bi_retention
    {_RETENTION_WHERE} AND d{max(RETENTION_DAYS)}_eligible
)
ARRAY JOIN [{", ".join(f"'Day {n}'" for n in RETENTION_DAYS)}] AS day, rates AS retention""".strip(),
                "bar",
                10,
                6,
                _RETENTION_FIELDS,
                viz=graph(["day"], ["retention"], pct=("retention",), graph__show_values=True),
                description=f"Only customers whose day {max(RETENTION_DAYS)} is inside the data, so "
                "every bar describes the same customers. Empty when the signup filter excludes all of them.",
            ),
            Card(
                "Retention by signup week",
                f"SELECT signup_week, count() AS new_customers, "
                f"{', '.join(f'{_rate(n)} AS d{n}' for n in RETENTION_DAYS)}\n"
                f"FROM bi_retention\n{_RETENTION_WHERE}\nGROUP BY signup_week\nORDER BY signup_week",
                "table",
                14,
                6,
                _RETENTION_FIELDS,
                viz=viz(
                    pct=tuple(f"d{n}" for n in RETENTION_DAYS),
                    titles={f"d{n}": f"Day {n}" for n in RETENTION_DAYS},
                ),
            ),
        ],
        [_retention_by("acquisition_channel", "acquisition channel"), _retention_by("platform", "platform")],
    ],
)


_RETURN_EVENT_FIELDS = {
    "date": ("events", "event_date"),
    "category": ("events", "category"),
    "city_tier": ("events", "city_tier"),
    "payment_method": ("events", "payment_method"),
    "platform": ("events", "platform"),
}
_RETURN_FIELDS = {
    key: ("bi_returns", "day" if key == "date" else col) for key, (_, col) in _RETURN_EVENT_FIELDS.items()
}
_RETURN_EVENT_WHERE = (
    "WHERE {{date}} AND {{category}} AND {{city_tier}} AND {{payment_method}} AND {{platform}}"
)


def _return_rate_by(dim: str, label: str, display: str = "bar") -> Card:
    return Card(
        f"Return rate by {label}",
        _sql(
            f"SELECT {dim}, ${{return_rate}} AS return_rate, ${{returns}} AS returns\n"
            f"FROM events\n{_RETURN_EVENT_WHERE}\nGROUP BY {dim}\nORDER BY return_rate DESC"
        ),
        display,
        12,
        6,
        _RETURN_EVENT_FIELDS,
        viz=graph([dim], ["return_rate"], pct=("return_rate",), graph__show_values=True),
    )


RETURNS = Dashboard(
    "Orbit · Returns",
    "Return rate, reasons and where returns come from.",
    [DATE, CATEGORY, CITY_TIER, PAYMENT, PLATFORM],
    [
        [
            Text(
                "**Returns.** Return rate follows Orbit: return-initiated order lines ÷ completed order "
                "lines in the same period. Returns lag orders by 3–14 days, so the first two weeks of data "
                "run low (there are no earlier orders to return)."
            )
        ],
        [
            _scalar(
                "Return rate",
                f"SELECT ${{return_rate}} AS return_rate FROM events {_RETURN_EVENT_WHERE}",
                _RETURN_EVENT_FIELDS,
                width=6,
                pct=("return_rate",),
            ),
            _scalar(
                "Returns",
                f"SELECT ${{returns}} AS returns FROM events {_RETURN_EVENT_WHERE}",
                _RETURN_EVENT_FIELDS,
                width=6,
            ),
            _scalar(
                "Returned value",
                f"SELECT sum(item_value) AS returned_value FROM bi_returns {_RETURN_EVENT_WHERE}",
                _RETURN_FIELDS,
                width=6,
                inr=("returned_value",),
            ),
            _scalar(
                "Returns completed",
                "SELECT if(count() = 0, NULL, countIf(completed) / count()) AS completed\n"
                f"FROM bi_returns {_RETURN_EVENT_WHERE}",
                _RETURN_FIELDS,
                width=6,
                pct=("completed",),
            ),
        ],
        [
            Card(
                "Return reasons",
                f"SELECT return_reason, count() AS returns\nFROM bi_returns\n{_RETURN_EVENT_WHERE}\n"
                "GROUP BY return_reason\nORDER BY returns DESC",
                "row",
                12,
                6,
                _RETURN_FIELDS,
                viz=graph(["return_reason"], ["returns"], graph__show_values=True),
            ),
            _return_rate_by("category", "category"),
        ],
        [
            _return_rate_by("city_tier", "city tier"),
            Card(
                "Return rate by week",
                _sql(
                    f"SELECT toStartOfWeek(event_date, 1) AS week, ${{return_rate}} AS return_rate\n"
                    f"FROM events\n{_RETURN_EVENT_WHERE}\nGROUP BY week\nORDER BY week"
                ),
                "line",
                12,
                6,
                _RETURN_EVENT_FIELDS,
                viz=graph(["week"], ["return_rate"], pct=("return_rate",), graph__x_axis__title_text=""),
            ),
        ],
        [
            Card(
                "Return reasons by category",
                f"SELECT category, return_reason, count() AS returns, sum(item_value) AS returned_value\n"
                f"FROM bi_returns\n{_RETURN_EVENT_WHERE}\nGROUP BY category, return_reason\n"
                "ORDER BY category, returns DESC",
                "table",
                24,
                6,
                _RETURN_FIELDS,
                viz=viz(inr=("returned_value",)),
            )
        ],
    ],
)


_ACQ_SESSION_FIELDS = {"date": ("events", "event_date"), "channel": ("events", "traffic_source")}
_ACQ_SESSIONS = f"({session_rollup('{{date}} AND {{channel}}')})"
_ACQ_FIELDS = {"date": ("bi_acquisition", "day"), "channel": ("bi_acquisition", "traffic_source")}

ACQUISITION = Dashboard(
    "Orbit · Acquisition",
    "Channels to users, conversion and revenue.",
    [DATE, CHANNEL],
    [
        [
            Text(
                "**Acquisition.** Orbit records the traffic source of every session and the acquisition "
                "source of every customer. Medium and campaign aren't collected, so channel is the finest "
                "level available."
            )
        ],
        [
            Card(
                "Channel performance",
                _sql(f"""
SELECT traffic_source AS channel,
    ${{sessions}} AS sessions,
    ${{users}} AS users,
    if(count() = 0, NULL, countIf(user_type = 'new') / count()) AS new_customer_share,
    ${{conversion}} AS conversion,
    sum(revenue) AS channel_revenue,
    if(count() = 0, NULL, sum(revenue) / count()) AS revenue_per_session
FROM {_ACQ_SESSIONS}
GROUP BY channel
ORDER BY channel_revenue DESC"""),
                "table",
                24,
                9,
                _ACQ_SESSION_FIELDS,
                viz=viz(
                    pct=("new_customer_share", "conversion"),
                    inr=("channel_revenue", "revenue_per_session"),
                    titles={
                        "new_customer_share": "New-customer sessions",
                        "channel_revenue": "Revenue",
                        "revenue_per_session": "Revenue / session",
                    },
                ),
            )
        ],
        [
            Card(
                "Sessions by channel, weekly",
                "SELECT toStartOfWeek(day, 1) AS week, traffic_source AS channel, sum(sessions) AS sessions\n"
                "FROM bi_acquisition\nWHERE {{date}} AND {{channel}}\n"
                "GROUP BY week, channel\nORDER BY week, channel",
                "bar",
                12,
                6,
                _ACQ_FIELDS,
                viz=graph(
                    ["week", "channel"],
                    ["sessions"],
                    stackable__stack_type="stacked",
                    graph__x_axis__title_text="",
                ),
            ),
            Card(
                "New customers by acquisition source, weekly",
                "SELECT toStartOfWeek(day, 1) AS week, traffic_source AS channel,\n"
                "    sum(signups) AS new_customers\n"
                "FROM bi_acquisition\nWHERE {{date}} AND {{channel}}\nGROUP BY week, channel\n"
                "HAVING new_customers > 0\nORDER BY week, channel",
                "bar",
                12,
                6,
                _ACQ_FIELDS,
                viz=graph(
                    ["week", "channel"],
                    ["new_customers"],
                    stackable__stack_type="stacked",
                    graph__x_axis__title_text="",
                ),
            ),
        ],
        [
            Card(
                "Revenue by channel",
                f"SELECT traffic_source AS channel, sum(revenue) AS revenue\nFROM {_ACQ_SESSIONS}\n"
                "GROUP BY channel\nORDER BY revenue DESC",
                "row",
                12,
                6,
                _ACQ_SESSION_FIELDS,
                viz=graph(["channel"], ["revenue"], inr=("revenue",)),
            ),
            Card(
                "Conversion rate by channel",
                _sql(
                    f"SELECT traffic_source AS channel, ${{conversion}} AS conversion\nFROM {_ACQ_SESSIONS}\n"
                    "GROUP BY channel\nORDER BY conversion DESC"
                ),
                "bar",
                12,
                6,
                _ACQ_SESSION_FIELDS,
                viz=graph(["channel"], ["conversion"], pct=("conversion",), graph__show_values=True),
            ),
        ],
    ],
)


_EXP_FIELDS = {"experiment": ("bi.experiments", "experiment")}
_RESULT_FIELDS = {"experiment": ("bi.experiment_results", "experiment")}


def _variant_values(metric_key: str, name: str, fmt: dict[str, Any]) -> Card:
    return Card(
        name,
        "SELECT experiment, variant, value\nFROM bi.experiment_results\n"
        f"WHERE metric_key = '{metric_key}' AND {{{{experiment}}}}\n"
        "ORDER BY experiment, is_control DESC, variant",
        "bar",
        24,
        6,
        _RESULT_FIELDS,
        database="postgres",
        viz=graph(
            ["experiment", "variant"],
            ["value"],
            formats={"value": fmt},
            graph__show_values=True,
            graph__y_axis__title_text=name.removesuffix(" by variant"),
        ),
    )


EXPERIMENTS = Dashboard(
    "Orbit · Experiments",
    "Exposures, variant results and statistical readouts from Orbit's experiment engine.",
    [EXPERIMENT],
    [
        [
            Text(
                "**Experiments.** Readouts come from Orbit's experiment engine: the same exposures, tests "
                "and recommendation as Orbit's Experiments page, refreshed daily by the worker. Conversion "
                "rate and revenue per exposed user are shown for every experiment, measured from each "
                "user's first exposure. Decisions stay in Orbit.",
                height=3,
            )
        ],
        [
            Card(
                "Experiments",
                """
SELECT experiment, status,
    (SELECT r.metric FROM bi.experiment_results r
     WHERE r.experiment_key = experiments.experiment_key AND r.role = 'primary' LIMIT 1) AS primary_metric,
    exposed_users, days_running,
    CASE WHEN srm_mismatch THEN 'Sample ratio mismatch' ELSE 'OK' END AS traffic_split,
    recommendation, confidence, headline, as_of AS results_as_of
FROM bi.experiments
WHERE {{experiment}}
ORDER BY start_date DESC""".strip(),
                "table",
                24,
                5,
                _EXP_FIELDS,
                database="postgres",
            )
        ],
        [_variant_values("conversion", "Conversion rate by variant", _PCT)],
        [_variant_values("revenue", "Revenue per exposed user by variant", _INR | {"decimals": 2})],
        [
            Card(
                "Statistical results",
                """
SELECT experiment, role, metric, variant, users,
    CASE format
        WHEN 'percent' THEN to_char(value * 100, 'FM990.00') || '%'
        WHEN 'currency' THEN '₹' || to_char(value, 'FM999,999,990.00')
        ELSE to_char(value, 'FM999,999,990.00')
    END AS value,
    lift,
    CASE WHEN lift_ci_low IS NOT NULL
        THEN to_char(lift_ci_low * 100, 'FMS990.0') || '% to '
            || to_char(lift_ci_high * 100, 'FMS990.0') || '%'
    END AS lift_95_ci,
    p_value,
    CASE WHEN is_control THEN 'control' WHEN significant THEN 'significant' ELSE 'not significant' END
        AS result
FROM bi.experiment_results
WHERE {{experiment}}
ORDER BY experiment, CASE role WHEN 'primary' THEN 0 WHEN 'guardrail' THEN 1 ELSE 2 END, metric,
    is_control DESC, variant""".strip(),
                "table",
                24,
                8,
                _RESULT_FIELDS,
                database="postgres",
                viz=viz(
                    pct=("lift",), titles={"lift_95_ci": "Lift 95% CI"}, formats={"p_value": {"decimals": 4}}
                ),
            )
        ],
        [
            Card(
                "Exposed users over time",
                "SELECT day, experiment || ' · ' || variant AS series, cumulative_users\n"
                "FROM bi.experiment_exposures\nWHERE {{experiment}}\nORDER BY day, series",
                "line",
                24,
                6,
                {"experiment": ("bi.experiment_exposures", "experiment")},
                database="postgres",
                viz=graph(["day", "series"], ["cumulative_users"], graph__x_axis__title_text=""),
            )
        ],
    ],
)

DASHBOARDS = [OVERVIEW, FUNNEL, RETENTION, RETURNS, ACQUISITION, EXPERIMENTS]
