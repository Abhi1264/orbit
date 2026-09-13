"""Deterministic synthetic dataset generator.

    python -m probelens.seed --profile demo --seed 42
    python -m probelens.seed --profile full --seed 42 --end-date 2026-09-13

Profiles trade volume for load time; both contain every scenario.
"""

import argparse
import random
import sys
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from probelens.analytics.anomalies import run_detection
from probelens.core.logging import configure_logging, get_logger
from probelens.db.clickhouse import get_readwrite_client
from probelens.db.postgres import get_sessionmaker
from probelens.db.redis import invalidate_analytics_cache
from probelens.seed.catalog import apply_stockout_risk, generate_products
from probelens.seed.load_clickhouse import load_events, load_user_profiles, reset_tables
from probelens.seed.population import generate_users
from probelens.seed.postgres_seed import link_anomalies_to_investigations, seed_postgres
from probelens.seed.scenarios import Scenarios
from probelens.seed.simulate import Simulator
from probelens.services.projects import default_project_id

log = get_logger("seed")

@dataclass(frozen=True)
class Profile:
    users: int
    products: int
    days: int

PROFILES = {
    "dev": Profile(users=4_000, products=1_000, days=56),
    "demo": Profile(users=30_000, products=3_000, days=84),
    "full": Profile(users=50_000, products=5_000, days=140),
}

def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--profile", choices=PROFILES, default="demo")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--users", type=int, help="override profile user count")
    parser.add_argument("--products", type=int, help="override profile product count")
    parser.add_argument("--days", type=int, help="override profile window length")
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=date.today(),
        help="last day of data (default: today)",
    )
    parser.add_argument("--skip-postgres", action="store_true")
    parser.add_argument("--skip-clickhouse", action="store_true")
    return parser.parse_args(argv)

def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = parse_args(argv if argv is not None else sys.argv[1:])
    profile = PROFILES[args.profile]
    n_users = args.users or profile.users
    n_products = args.products or profile.products
    days = args.days or profile.days
    end = args.end_date
    start = end - timedelta(days=days - 1)
    sc = Scenarios(start=start, end=end)

    log.info(
        "seed_start",
        profile=args.profile,
        seed=args.seed,
        users=n_users,
        products=n_products,
        start=str(start),
        end=str(end),
    )
    started = time.perf_counter()

    rng = random.Random(args.seed)
    products = apply_stockout_risk(rng, generate_products(rng, n_products))
    users = generate_users(
        rng, n_users, start, end, campaign_start=sc.day(sc.paid_social_campaign_start_days_before_end)
    )
    sim = Simulator(rng, users, products, start, end, sc)

    total_events = 0
    if not args.skip_clickhouse:
        ch = get_readwrite_client()
        reset_tables(ch)

        def progress(day: date, count: int) -> None:
            nonlocal total_events
            total_events += count
            if day.weekday() == 6 or day == end:
                log.info("seed_progress", day=str(day), events_so_far=total_events)

        load_events(ch, sim.run(on_progress=progress))
        # Profiles are written after simulation so first_purchase_date is known.
        load_user_profiles(ch, users)
        log.info("seed_clickhouse_done", events=total_events, users=len(users))
    else:
        for _ in sim.run():
            pass

    if not args.skip_postgres:
        db = get_sessionmaker()()
        try:
            summary = seed_postgres(db, products, sc)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        log.info("seed_postgres_done", **{k: v for k, v in summary.items() if k != "users"})

    invalidate_analytics_cache()

    if not args.skip_postgres and not args.skip_clickhouse:
        # Run the anomaly sweep now so the inbox is populated the moment the app opens.
        db = get_sessionmaker()()
        try:
            project_id = default_project_id(db)
            detection = run_detection(db, project_id, end, datetime.now(UTC))
            detection["linked"] = link_anomalies_to_investigations(db, project_id)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        log.info("seed_anomalies_done", **detection)
    log.info("seed_complete", seconds=round(time.perf_counter() - started, 1), events=total_events)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
