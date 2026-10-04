import argparse
import secrets
import sys
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from psycopg import sql as pgsql
from sqlalchemy import text
from sqlalchemy.engine import make_url

from probelens.bi.dashboards import DASHBOARDS, OVERVIEW, Card, Dashboard, Filter, Text, with_titles
from probelens.bi.metabase import Metabase, MetabaseError
from probelens.bi.status import record_provisioning
from probelens.bi.views import VIEWS, apply_views
from probelens.config import get_settings
from probelens.core.logging import configure_logging, get_logger
from probelens.db.clickhouse import get_readwrite_client
from probelens.db.postgres import get_engine

log = get_logger("bi.provision")

BI_USER = "orbit_bi"
COLLECTION = "Orbit"
SITE_NAME = "Orbit BI"
DATABASE_NAMES = {"clickhouse": "Orbit events (ClickHouse)", "postgres": "Orbit experiments (Postgres)"}
SYNC_TIMEOUT_SECONDS = 180
# Stable ids keep dashboard filter URLs and template tags unchanged across runs.
_ID_NAMESPACE = uuid.UUID("9d0c6b0e-4f3a-4f7e-8b8e-2f6c1a7d5e41")


def _stable_id(*parts: str) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, "|".join(parts)))


def create_clickhouse_user(password: str) -> None:
    client = get_readwrite_client()
    client.command(
        f"CREATE USER OR REPLACE {BI_USER} IDENTIFIED WITH sha256_password BY %(pw)s "
        "SETTINGS PROFILE 'bi_analytics'",
        parameters={"pw": password},
    )
    client.command(f"GRANT SELECT ON {get_settings().clickhouse_database}.* TO {BI_USER}")


def create_postgres_role(password: str) -> None:
    engine = get_engine()
    database = make_url(get_settings().database_url).database
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": BI_USER}).scalar()
        raw = conn.connection.dbapi_connection
        statements = [
            pgsql.SQL("{} ROLE {} WITH LOGIN PASSWORD {}").format(
                pgsql.SQL("ALTER" if exists else "CREATE"), pgsql.Identifier(BI_USER), pgsql.Literal(password)
            ),
            pgsql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(
                pgsql.Identifier(BI_USER)
            ),
            pgsql.SQL("ALTER ROLE {} SET statement_timeout = '60s'").format(pgsql.Identifier(BI_USER)),
            pgsql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                pgsql.Identifier(database), pgsql.Identifier(BI_USER)
            ),
            pgsql.SQL("GRANT USAGE ON SCHEMA bi TO {}").format(pgsql.Identifier(BI_USER)),
            pgsql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA bi TO {}").format(pgsql.Identifier(BI_USER)),
            pgsql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA bi GRANT SELECT ON TABLES TO {}").format(
                pgsql.Identifier(BI_USER)
            ),
        ]
        for statement in statements:
            conn.exec_driver_sql(statement.as_string(raw))


def connect_database(mb: Metabase, engine: str, details: dict[str, Any]) -> int:
    name = DATABASE_NAMES[engine]
    existing = next((d for d in mb.databases() if d["name"] == name), None)
    if existing:
        mb.put(f"/database/{existing['id']}", {"details": details})
        database_id = existing["id"]
    else:
        database_id = mb.post("/database", {"engine": engine, "name": name, "details": details})["id"]
    mb.post(f"/database/{database_id}/sync_schema")
    return database_id


def wait_for_fields(
    mb: Metabase, database_id: int, needed: set[tuple[str, str]]
) -> dict[tuple[str, str], int]:
    deadline = time.monotonic() + SYNC_TIMEOUT_SECONDS
    while True:
        tables = mb.tables(database_id)
        found = {
            (table, column): field["id"]
            for table, column in needed
            for field in tables.get(table, {}).get("fields", [])
            if field["name"] == column
        }
        if len(found) == len(needed):
            return found
        if time.monotonic() > deadline:
            missing = sorted(f"{t}.{c}" for t, c in needed - found.keys())
            raise MetabaseError(f"Metabase sync did not pick up: {', '.join(missing)}")
        time.sleep(2)


def ensure_collection(mb: Metabase) -> int:
    for collection in mb.get("/collection"):
        if (
            collection.get("name") == COLLECTION
            and collection.get("location") == "/"
            and not collection.get("archived")
            and collection.get("personal_owner_id") is None
        ):
            return collection["id"]
    return mb.post(
        "/collection",
        {
            "name": COLLECTION,
            "description": "Dashboards provisioned from Orbit (python -m probelens.bi.provision).",
        },
    )["id"]


def _parameter(dashboard: Dashboard, f: Filter) -> dict[str, Any]:
    kind = "date/all-options" if f.kind == "date" else "string/="
    return {
        "id": _stable_id(dashboard.name, f.slug),
        "name": f.name,
        "slug": f.slug,
        "type": kind,
        "sectionId": "date" if f.kind == "date" else "string",
    }


def _used_filters(dashboard: Dashboard, card: Card) -> list[Filter]:
    return [f for f in dashboard.filters if f.slug in card.fields and f"{{{{{f.slug}}}}}" in card.sql]


def _result_columns(card: dict[str, Any] | None) -> list[str]:
    return [column["name"] for column in (card or {}).get("result_metadata") or []]


def card_payload(
    dashboard: Dashboard,
    card: Card,
    database_id: int,
    fields: dict[tuple[str, str], int],
    collection_id: int,
    dashboard_id: int,
    columns: list[str],
) -> dict[str, Any]:
    tags = {
        f.slug: {
            "id": _stable_id(dashboard.name, card.name, f.slug),
            "name": f.slug,
            "display-name": f.name,
            "type": "dimension",
            "dimension": ["field", fields[card.fields[f.slug]], None],
            "widget-type": "date/all-options" if f.kind == "date" else "string/=",
        }
        for f in _used_filters(dashboard, card)
    }
    return {
        "name": card.name,
        "description": card.description or None,
        "display": card.display,
        "collection_id": collection_id,
        "dashboard_id": dashboard_id,
        "visualization_settings": with_titles(card.viz, columns),
        "dataset_query": {
            "type": "native",
            "database": database_id,
            "native": {"query": card.sql, "template-tags": tags},
        },
    }


def upsert_dashboard(
    mb: Metabase,
    dashboard: Dashboard,
    collection_id: int,
    databases: dict[str, int],
    fields: dict[tuple[str, str], int],
) -> dict[str, Any]:
    items = mb.get(f"/collection/{collection_id}/items", models="dashboard")
    items = items["data"] if isinstance(items, dict) else items
    found = next((d for d in items if d["name"] == dashboard.name), None)
    if found:
        dashboard_id = found["id"]
    else:
        dashboard_id = mb.post(
            "/dashboard",
            {"name": dashboard.name, "description": dashboard.description, "collection_id": collection_id},
        )["id"]
    existing_cards = {
        c["name"]: c
        for c in mb.get("/card", f="all")
        if c.get("dashboard_id") == dashboard_id and not c.get("archived")
    }

    dashcards: list[dict[str, Any]] = []
    y = 0
    for row in dashboard.rows:
        x = 0
        for item in row:
            placement = {
                "id": -(len(dashcards) + 1),
                "row": y,
                "col": x,
                "size_x": item.width,
                "size_y": item.height,
            }
            if isinstance(item, Text):
                dashcards.append(
                    placement
                    | {
                        "card_id": None,
                        "parameter_mappings": [],
                        "visualization_settings": {
                            "virtual_card": {
                                "name": None,
                                "display": "text",
                                "visualization_settings": {},
                                "dataset_query": {},
                                "archived": False,
                            },
                            "text": item.markdown,
                        },
                    }
                )
            else:
                # Column titles need the result columns, which Metabase reports once a card is saved.
                current = existing_cards.pop(item.name, None)
                columns = _result_columns(current)
                payload = card_payload(
                    dashboard, item, databases[item.database], fields, collection_id, dashboard_id, columns
                )
                card = mb.put(f"/card/{current['id']}", payload) if current else mb.post("/card", payload)
                card_id = card["id"]
                if _result_columns(card) != columns:
                    viz = with_titles(item.viz, _result_columns(card))
                    mb.put(f"/card/{card_id}", {"visualization_settings": viz})
                dashcards.append(
                    placement
                    | {
                        "card_id": card_id,
                        "visualization_settings": {},
                        "parameter_mappings": [
                            {
                                "parameter_id": _stable_id(dashboard.name, f.slug),
                                "card_id": card_id,
                                "target": ["dimension", ["template-tag", f.slug]],
                            }
                            for f in _used_filters(dashboard, item)
                        ],
                    }
                )
            x += item.width
        y += max(item.height for item in row)

    saved = mb.put(
        f"/dashboard/{dashboard_id}",
        {
            "name": dashboard.name,
            "description": dashboard.description,
            "parameters": [_parameter(dashboard, f) for f in dashboard.filters],
            "dashcards": dashcards,
        },
    )
    for stale in existing_cards.values():
        mb.put(f"/card/{stale['id']}", {"archived": True})
    return {"id": dashboard_id, "name": dashboard.name, "dashcards": saved["dashcards"]}


def verify_dashboard(mb: Metabase, saved: dict[str, Any]) -> list[str]:
    failures = []
    for dashcard in saved["dashcards"]:
        card_id = dashcard.get("card_id")
        if not card_id:
            continue
        name = (dashcard.get("card") or {}).get("name", card_id)
        path = f"/dashboard/{saved['id']}/dashcard/{dashcard['id']}/card/{card_id}/query"
        try:
            result = mb.post(path, {"parameters": []})
        except MetabaseError as exc:
            failures.append(f"{saved['name']} / {name}: {str(exc)[:300]}")
            continue
        if result.get("status") != "completed":
            failures.append(f"{saved['name']} / {name}: {str(result.get('error'))[:300]}")
    return failures


def remove_sample_content(mb: Metabase) -> None:
    for collection in mb.get("/collection"):
        if collection.get("is_sample") and not collection.get("archived"):
            mb.put(f"/collection/{collection['id']}", {"archived": True})
    for database in mb.databases():
        if database.get("is_sample"):
            mb.request("DELETE", f"/database/{database['id']}")


def provision(clickhouse_host: str, postgres_host: str) -> dict[str, Any]:
    settings = get_settings()
    mb = Metabase(settings.metabase_url)
    try:
        mb.wait_healthy()
        first_run = mb.login(settings.metabase_admin_email, settings.metabase_admin_password, SITE_NAME)
        if first_run:
            remove_sample_content(mb)

        views = apply_views(get_readwrite_client())
        ch_password, pg_password = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        create_clickhouse_user(ch_password)
        create_postgres_role(pg_password)
        log.info("bi_identities_ready", user=BI_USER, views=views)

        pg_url = make_url(settings.database_url)
        databases = {
            "clickhouse": connect_database(
                mb,
                "clickhouse",
                {
                    "host": clickhouse_host,
                    "port": settings.clickhouse_port,
                    "dbname": settings.clickhouse_database,
                    "user": BI_USER,
                    "password": ch_password,
                    "enable-multiple-db": False,
                    "ssl": False,
                },
            ),
            "postgres": connect_database(
                mb,
                "postgres",
                {
                    "host": postgres_host,
                    "port": pg_url.port or 5432,
                    "dbname": pg_url.database,
                    "user": BI_USER,
                    "password": pg_password,
                    "schema-filters-type": "inclusion",
                    "schema-filters-patterns": "bi",
                    "ssl": False,
                },
            ),
        }
        fields: dict[tuple[str, str], int] = {}
        for engine, database_id in databases.items():
            needed = {
                pair
                for d in DASHBOARDS
                for c in d.cards
                if c.database == engine
                for pair in c.fields.values()
            }
            fields |= wait_for_fields(mb, database_id, needed)
        for database_id in databases.values():
            mb.post(f"/database/{database_id}/rescan_values")

        collection_id = ensure_collection(mb)
        saved = [upsert_dashboard(mb, d, collection_id, databases, fields) for d in DASHBOARDS]
        overview_id = next(s["id"] for s in saved if s["name"] == OVERVIEW.name)
        mb.put("/setting/custom-homepage", {"value": True})
        mb.put("/setting/custom-homepage-dashboard", {"value": overview_id})

        failures = [f for s in saved for f in verify_dashboard(mb, s)]
        if failures:
            raise MetabaseError("Cards failed to run:\n  " + "\n  ".join(failures))

        version = mb.get("/session/properties").get("version", {}).get("tag")
    finally:
        mb.close()

    record = {
        "provisioned_at": datetime.now(UTC).isoformat(),
        "metabase_version": version,
        "collection_id": collection_id,
        "dashboards": [
            {"id": s["id"], "name": s["name"], "cards": sum(1 for dc in s["dashcards"] if dc.get("card_id"))}
            for s in saved
        ],
        "views": sorted(VIEWS),
    }
    record_provisioning(record)
    return record


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    settings = get_settings()
    parser = argparse.ArgumentParser(
        prog="python -m probelens.bi.provision",
        description="Create or update Orbit's Metabase databases, questions and dashboards.",
    )
    parser.add_argument("--clickhouse-host", default="clickhouse", help="ClickHouse host as Metabase sees it")
    parser.add_argument("--postgres-host", default="postgres", help="Postgres host as Metabase sees it")
    args = parser.parse_args(argv)

    missing = [
        name
        for name, value in [
            ("METABASE_URL", settings.metabase_url),
            ("METABASE_ADMIN_EMAIL", settings.metabase_admin_email),
            ("METABASE_ADMIN_PASSWORD", settings.metabase_admin_password),
        ]
        if not value
    ]
    if missing:
        print(f"Set {', '.join(missing)} in .env first (see README).", file=sys.stderr)
        return 2
    try:
        record = provision(args.clickhouse_host, args.postgres_host)
    except MetabaseError as exc:
        log.error("bi_provision_failed", error=str(exc))
        return 1
    log.info(
        "bi_provision_done",
        dashboards=[d["name"] for d in record["dashboards"]],
        cards=sum(d["cards"] for d in record["dashboards"]),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
