from collections.abc import Iterable
from datetime import date

from clickhouse_connect.driver.client import Client

from probelens.core.logging import get_logger
from probelens.seed.population import SimUser
from probelens.seed.simulate import EVENT_COLUMNS

log = get_logger("seed.clickhouse")

INSERT_BATCH = 100_000

USER_PROFILE_COLUMNS = [
    "user_id",
    "signup_date",
    "first_purchase_date",
    "acquisition_source",
    "primary_platform",
    "country",
    "city_tier",
    "preferred_payment",
]


def reset_tables(client: Client) -> None:
    client.command("TRUNCATE TABLE events")
    client.command("TRUNCATE TABLE user_profiles")


def load_events(client: Client, batches: Iterable[list[tuple]]) -> int:
    """Insert rows in ~100k-row batches (per ClickHouse insert-batch guidance)."""
    buffer: list[tuple] = []
    total = 0
    for rows in batches:
        buffer.extend(rows)
        if len(buffer) >= INSERT_BATCH:
            client.insert("events", buffer, column_names=EVENT_COLUMNS)
            total += len(buffer)
            buffer = []
    if buffer:
        client.insert("events", buffer, column_names=EVENT_COLUMNS)
        total += len(buffer)
    return total


def load_user_profiles(client: Client, users: list[SimUser]) -> None:
    epoch = date(1970, 1, 1)
    rows = [
        (
            u.id,
            u.signup_date,
            u.first_purchase_date or epoch,
            u.acquisition_source,
            u.platform,
            u.country,
            u.city_tier,
            u.payment_method,
        )
        for u in users
    ]
    for i in range(0, len(rows), INSERT_BATCH):
        client.insert("user_profiles", rows[i : i + INSERT_BATCH], column_names=USER_PROFILE_COLUMNS)
