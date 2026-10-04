import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterator
from datetime import date, timedelta

from clickhouse_connect.driver.client import Client
from sqlalchemy import select

from probelens.analytics.sql import NOT_POST_PURCHASE
from probelens.config import get_settings
from probelens.core.logging import configure_logging, get_logger
from probelens.db.clickhouse import get_readonly_client
from probelens.db.postgres import get_sessionmaker
from probelens.models.core import Product
from probelens.seed.simulate import EVENT_COLUMNS
from probelens.tracking import status, taxonomy
from probelens.tracking.amplitude import AmplitudeSink
from probelens.tracking.mapping import AmplitudeMapper, UserTraits
from probelens.tracking.pipeline import EventPipeline

log = get_logger("tracking.backfill")

# The read-only profile truncates large results; a day of sessions must arrive whole.
_UNCAPPED = {"max_result_rows": 0, "max_execution_time": 120}

_SESSIONS_STARTING_ON = f"""
SELECT {", ".join(EVENT_COLUMNS)}
FROM events
WHERE event_date >= {{day:Date}}
  AND session_id IN (
    SELECT session_id FROM events
    WHERE event_date BETWEEN {{day:Date}} - 1 AND {{day:Date}} AND {NOT_POST_PURCHASE}
    GROUP BY session_id
    HAVING toDate(min(timestamp)) = {{day:Date}}
  )
"""


def load_traits(ch: Client, user_ids: list[int] | None = None) -> dict[int, UserTraits]:
    sql = "SELECT user_id, acquisition_source, signup_date, preferred_payment FROM user_profiles FINAL"
    if user_ids is not None:
        sql += " WHERE user_id IN {ids:Array(UInt64)}"
    result = ch.query(sql, parameters={"ids": user_ids}, settings=_UNCAPPED)
    return {uid: UserTraits(source, signup, payment) for uid, source, signup, payment in result.result_rows}


def load_prices() -> dict[int, float]:
    with get_sessionmaker()() as db:
        return {pid: float(price) for pid, price in db.execute(select(Product.id, Product.price))}


def data_range(ch: Client) -> tuple[date, date] | None:
    sql = f"SELECT min(event_date), max(event_date) FROM events WHERE {NOT_POST_PURCHASE}"
    first, last = ch.query(sql).first_row
    return None if first == date(1970, 1, 1) else (first, last)


def day_batches(ch: Client, start: date, end: date) -> Iterator[list[tuple]]:
    day = start
    while day <= end:
        rows = ch.query(_SESSIONS_STARTING_ON, parameters={"day": day}, settings=_UNCAPPED).result_rows
        log.info("backfill_day", day=str(day), rows=len(rows))
        yield rows
        day += timedelta(days=1)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send the events already in ClickHouse to Amplitude.")
    parser.add_argument("--days", type=int, help="only the last N days of data")
    parser.add_argument("--dry-run", action="store_true", help="map events and print a summary; send nothing")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = parse_args(argv if argv is not None else sys.argv[1:])
    settings = get_settings()
    if not args.dry_run and not settings.amplitude_enabled:
        log.error("amplitude_not_configured", hint="set AMPLITUDE_API_KEY, or use --dry-run")
        return 2

    ch = get_readonly_client()
    span = data_range(ch)
    if span is None:
        log.error("no_events", hint="seed ClickHouse first: make seed")
        return 1
    start, end = span
    if args.days:
        start = max(start, end - timedelta(days=args.days - 1))
    mapper = AmplitudeMapper(load_prices(), load_traits(ch))
    log.info("backfill_start", start=str(start), end=str(end), dry_run=args.dry_run)

    if args.dry_run:
        counts: Counter[str] = Counter()
        sample = None
        for rows in day_batches(ch, start, end):
            events = mapper.map(rows)
            counts.update(e.event_type for e in events)
            sample = sample or next((e for e in events if e.event_type == taxonomy.ORDER_PLACED), None)
        log.info("backfill_dry_run", events=sum(counts.values()), by_type=dict(counts.most_common()))
        if sample:
            print(json.dumps(sample.to_dict(), indent=2, default=str))
        return 0

    sink = AmplitudeSink(settings.amplitude_api_key, mapper, server_zone=settings.amplitude_server_zone)
    [report] = EventPipeline([sink]).run(day_batches(ch, start, end))
    status.record_export(report, source="backfill", recent=sink.recent())
    log.info("backfill_done", **report.as_dict())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
