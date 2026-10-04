from datetime import date

from clickhouse_connect.driver.client import Client

from probelens.core.logging import get_logger
from probelens.seed.population import SimUser
from probelens.seed.simulate import EVENT_COLUMNS
from probelens.tracking.pipeline import SinkReport

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


class ClickHouseSink:
    name = "clickhouse"

    def __init__(self, client: Client, batch_rows: int = INSERT_BATCH) -> None:
        self.client = client
        self.batch_rows = batch_rows
        self.inserted = 0
        self._pending: list[list[tuple]] = []
        self._pending_rows = 0

    def write(self, rows: list[tuple]) -> list[list[tuple]]:
        self._pending.append(rows)
        self._pending_rows += len(rows)
        return self.flush() if self._pending_rows >= self.batch_rows else []

    def flush(self) -> list[list[tuple]]:
        batches, self._pending, self._pending_rows = self._pending, [], 0
        rows = [row for batch in batches for row in batch]
        if rows:
            self.client.insert("events", rows, column_names=EVENT_COLUMNS)
            self.inserted += len(rows)
        return batches

    def report(self) -> SinkReport:
        return SinkReport(self.name, ok=True, rows=self.inserted, sent=self.inserted, delivered=self.inserted)


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
