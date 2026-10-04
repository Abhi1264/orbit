from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any

import pytest

from probelens.bi.dashboards import ACQUISITION, DASHBOARDS, FUNNEL, OVERVIEW, Card, graph, viz, with_titles
from probelens.bi.views import FUNNEL_STEPS, VIEWS
from tests.util import require_db

TAG = re.compile(r"\{\{(\w+)\}\}")
OPTIONAL = re.compile(r"\[\[(.*?)\]\]", re.S)
GRID_COLUMNS = 24

CARDS = [(d, c) for d in DASHBOARDS for c in d.cards]


def col(name: str) -> str:
    return json.dumps(["name", name], separators=(",", ":"))


@pytest.mark.parametrize(("dashboard", "card"), CARDS, ids=[f"{d.name} / {c.name}" for d, c in CARDS])
def test_cards_only_use_declared_dashboard_filters(dashboard, card) -> None:
    tags = set(TAG.findall(card.sql))
    assert tags <= set(card.fields), "template tag without a field to filter on"
    assert tags <= {f.slug for f in dashboard.filters}, "template tag without a dashboard filter"
    assert "${" not in card.sql, "unsubstituted Orbit metric"


def test_dashboards_are_well_formed() -> None:
    for dashboard in DASHBOARDS:
        names = [c.name for c in dashboard.cards]
        assert len(names) == len(set(names)), f"{dashboard.name}: the provisioner matches cards by name"
        for f in dashboard.filters:
            assert any(f"{{{{{f.slug}}}}}" in c.sql for c in dashboard.cards), (
                f"{dashboard.name}: {f.slug} unused"
            )
        for row in dashboard.rows:
            assert sum(item.width for item in row) <= GRID_COLUMNS, dashboard.name


def test_visualization_helpers_merge_instead_of_replacing() -> None:
    settings = viz(pct=("lift",), titles={"lift_95_ci": "Lift 95% CI"}, formats={"p_value": {"decimals": 4}})
    assert settings["column_settings"][col("lift")]["number_style"] == "percent"
    assert settings["column_settings"][col("p_value")] == {"decimals": 4}

    titled = with_titles(settings, ["experiment", "lift_95_ci", "p_value"])["column_settings"]
    assert titled[col("experiment")] == {"column_title": "Experiment"}
    assert titled[col("lift_95_ci")] == {"column_title": "Lift 95% CI"}
    assert titled[col("p_value")] == {"column_title": "p-value", "decimals": 4}

    chart = graph(["traffic_source"], ["search_to_order"], pct=("search_to_order",), graph__show_values=True)
    assert chart["graph.x_axis.title_text"] == "Channel"
    assert chart["graph.y_axis.title_text"] == "Search → order"
    assert chart["series_settings"] == {"search_to_order": {"title": "Search → order"}}
    assert chart["graph.show_values"] is True
    assert chart["column_settings"][col("search_to_order")]["number_style"] == "percent"


@pytest.fixture(scope="module")
def clickhouse():
    try:
        from probelens.bi.views import apply_views
        from probelens.db.clickhouse import get_readonly_client, get_readwrite_client
        from probelens.tracking.backfill import data_range

        apply_views(get_readwrite_client())
        client = get_readonly_client()
        span = data_range(client)
    except Exception as exc:
        require_db(f"ClickHouse not reachable: {exc}")
        return None
    if span is None:
        require_db("ClickHouse has no events; run the seed first")
    return client


@pytest.fixture(scope="module")
def span(clickhouse) -> tuple[date, date]:
    from probelens.tracking.backfill import data_range

    return data_range(clickhouse)


@pytest.fixture(scope="module")
def postgres():
    try:
        from sqlalchemy import text

        from probelens.db.postgres import get_engine

        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM bi.experiments LIMIT 1"))
    except Exception as exc:
        require_db(f"Postgres bi schema not reachable: {exc}")
        return None
    return engine


def render(card: Card, values: dict[str, Any] | None = None) -> str:
    from probelens.config import get_settings

    values = values or {}

    def field(slug: str) -> str:
        table, column = card.fields[slug]
        if card.database == "clickhouse":
            return f"`{get_settings().clickhouse_database}`.`{table}`.`{column}`"
        schema, name = table.split(".")
        return f'"{schema}"."{name}"."{column}"'

    def condition(match: re.Match) -> str:
        value = values.get(match.group(1))
        if value is None:
            return "1 = 1"
        if isinstance(value, tuple):
            return f"{field(match.group(1))} BETWEEN '{value[0]}' AND '{value[1]}'"
        return f"{field(match.group(1))} = '{value}'"

    def optional(match: re.Match) -> str:
        block = match.group(1)
        return block if all(values.get(tag) is not None for tag in TAG.findall(block)) else ""

    return TAG.sub(condition, OPTIONAL.sub(optional, card.sql))


def run(card: Card, clickhouse, postgres, values: dict[str, Any] | None = None) -> tuple[list[str], list]:
    sql = render(card, values)
    if card.database == "clickhouse":
        result = clickhouse.query(sql)
        return list(result.column_names), [list(r) for r in result.result_rows]
    from sqlalchemy import text

    with postgres.connect() as conn:
        result = conn.execute(text(sql))
        return list(result.keys()), [list(r) for r in result.fetchall()]


def card(dashboard, name: str) -> Card:
    return next(c for c in dashboard.cards if c.name == name)


def test_bi_views_exist(clickhouse) -> None:
    from probelens.config import get_settings

    tables = clickhouse.query(
        "SELECT name FROM system.tables WHERE database = {db:String}",
        parameters={"db": get_settings().clickhouse_database},
    ).result_columns[0]
    assert set(VIEWS) <= set(tables)


@pytest.mark.parametrize(("dashboard", "card_"), CARDS, ids=[f"{d.name} / {c.name}" for d, c in CARDS])
def test_every_card_runs_on_seeded_data(dashboard, card_, clickhouse, postgres) -> None:
    columns, rows = run(card_, clickhouse, postgres)
    assert rows, "no rows on seeded data"
    referenced = set(card_.viz.get("graph.dimensions", [])) | set(card_.viz.get("graph.metrics", []))
    referenced |= {json.loads(key)[1] for key in card_.viz.get("column_settings", {})}
    assert referenced <= set(columns)


OVERVIEW_METRICS = {
    "Orders": "orders",
    "Revenue": "revenue",
    "Conversion rate": "conversion",
    "Checkout conversion": "checkout_conversion",
    "Payment success rate": "payment_success_rate",
    "Return rate": "return_rate",
    "Active users": "users",
    "Sessions": "sessions",
    "Average order value": "aov",
}


def test_overview_numbers_are_orbits_numbers(clickhouse, postgres, span) -> None:
    from probelens.analytics.query import MetricQuery, run_metric_query

    start, end = span
    for period in [(start, end), (end - timedelta(days=13), end)]:
        for name, metric in OVERVIEW_METRICS.items():
            [[value]] = run(card(OVERVIEW, name), clickhouse, postgres, {"date": period})[1]
            query = MetricQuery(metric=metric, date_from=period[0], date_to=period[1], granularity=None)
            expected = run_metric_query(query).series[0].total.value
            assert value == pytest.approx(expected, rel=1e-9), (name, period)


def test_active_user_trends_are_orbits_active_users(clickhouse, postgres, span) -> None:
    from probelens.analytics.query import MetricQuery, run_metric_query

    end = span[1]
    columns, rows = run(card(OVERVIEW, "Daily, weekly and monthly active users"), clickhouse, postgres)
    last = dict(zip(columns, rows[-1], strict=True))
    assert last["day"] == end
    for column, days in [("DAU", 1), ("WAU", 7), ("MAU", 30)]:
        query = MetricQuery(
            metric="users", date_from=end - timedelta(days=days - 1), date_to=end, granularity=None
        )
        assert last[column] == run_metric_query(query).series[0].total.value, column


def test_funnel_matches_orbits_funnel_with_filters(clickhouse, postgres, span) -> None:
    from probelens.analytics.dimensions import Filter
    from probelens.analytics.funnel import FunnelQuery, FunnelSegment, run_funnel

    start, end = span
    recent = (end - timedelta(days=13), end)
    category, payment, channel = (
        clickhouse.query(
            f"SELECT {column} FROM events WHERE {column} != '' "
            f"GROUP BY {column} ORDER BY count() DESC LIMIT 1"
        ).result_rows[0][0]
        for column in ("category", "payment_method", "traffic_source")
    )
    cases = [
        ({}, (start, end), []),
        (
            {"date": recent, "platform": "android", "category": category},
            recent,
            [Filter(dimension="platform", value="android"), Filter(dimension="category", value=category)],
        ),
        (
            {"date": recent, "channel": channel, "city_tier": "tier1", "payment_method": payment},
            recent,
            [
                Filter(dimension="traffic_source", value=channel),
                Filter(dimension="city_tier", value="tier1"),
                Filter(dimension="payment_method", value=payment),
            ],
        ),
    ]
    for values, (date_from, date_to), filters in cases:
        rows = run(card(FUNNEL, "Search → order funnel"), clickhouse, postgres, values)[1]
        orbit = run_funnel(
            FunnelQuery(
                steps=FUNNEL_STEPS,
                date_from=date_from,
                date_to=date_to,
                segments=[FunnelSegment(filters=filters)],
            )
        )
        assert [r[1] for r in rows] == [step.sessions for step in orbit.series[0].steps], values


def test_channel_performance_matches_orbits_breakdowns(clickhouse, postgres, span) -> None:
    from probelens.analytics.query import MetricQuery, run_metric_query

    end = span[1]
    date_from, date_to = end - timedelta(days=13), end
    columns, rows = run(
        card(ACQUISITION, "Channel performance"), clickhouse, postgres, {"date": (date_from, date_to)}
    )
    table = [dict(zip(columns, row, strict=True)) for row in rows]
    for column, metric in [
        ("sessions", "sessions"),
        ("users", "users"),
        ("conversion", "conversion"),
        ("channel_revenue", "revenue"),
    ]:
        query = MetricQuery(
            metric=metric,
            date_from=date_from,
            date_to=date_to,
            breakdown="traffic_source",
            granularity=None,
            limit=50,
        )
        orbit = {s.key: s.total.value for s in run_metric_query(query).series}
        assert {r["channel"]: r[column] for r in table} == pytest.approx(orbit, rel=1e-9), metric


def test_bi_schema_flattens_orbits_experiment_readouts(postgres, clickhouse) -> None:
    from sqlalchemy import select, text
    from sqlalchemy.orm import Session, selectinload

    from probelens.experiments.analysis import analyze
    from probelens.experiments.spec import spec_from_model
    from probelens.models import Experiment
    from probelens.models.enums import ExperimentStatus

    with Session(postgres) as db:
        experiments = {
            e.key: e
            for e in db.scalars(
                select(Experiment)
                .options(selectinload(Experiment.variants))
                .where(Experiment.status != ExperimentStatus.draft)
            )
        }
        rows = db.execute(
            text("SELECT experiment_key, as_of, exposed_users, recommendation FROM bi.experiments")
        )
        rows = rows.mappings().all()
        assert experiments and {r["experiment_key"] for r in rows} == set(experiments)
        for r in rows:
            assert r["as_of"] is not None, f"{r['experiment_key']} has no snapshot"
            fresh = analyze(spec_from_model(experiments[r["experiment_key"]]), r["as_of"])
            assert r["exposed_users"] == fresh.exposure.total_users
            assert r["recommendation"] == fresh.recommendation.decision
            primary = next(m for m in fresh.metrics if m.role == "primary")
            stored = db.execute(
                text(
                    "SELECT variant, users, value FROM bi.experiment_results "
                    "WHERE experiment_key = :key AND role = 'primary'"
                ),
                {"key": r["experiment_key"]},
            ).all()
            expected = {v.key: (v.users, v.value) for v in primary.variants}
            assert {variant: (users, pytest.approx(value)) for variant, users, value in stored} == expected
