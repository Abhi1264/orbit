import argparse
import random
import sys
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from probelens.analytics.anomalies import run_detection
from probelens.config import get_settings
from probelens.core.logging import configure_logging, get_logger
from probelens.db.clickhouse import get_readwrite_client
from probelens.db.postgres import get_sessionmaker
from probelens.db.redis import invalidate_analytics_cache
from probelens.experiments.snapshots import snapshot_experiments
from probelens.seed.catalog import ProductRow, apply_stockout_risk, generate_products
from probelens.seed.load_clickhouse import ClickHouseSink, load_user_profiles, reset_tables
from probelens.seed.population import SimUser, generate_users
from probelens.seed.postgres_seed import link_anomalies_to_investigations, seed_postgres
from probelens.seed.scenarios import Scenarios
from probelens.seed.simulate import Simulator
from probelens.services.projects import default_project_id
from probelens.tracking import status as tracking_status
from probelens.tracking.amplitude import AmplitudeSink
from probelens.tracking.mapping import AmplitudeMapper, UserTraits
from probelens.tracking.pipeline import EventPipeline

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
    parser = argparse.ArgumentParser(description="Simulate the storefront and load Postgres and ClickHouse.")
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
    parser.add_argument(
        "--no-amplitude", action="store_true", help="do not send events to Amplitude even if it is configured"
    )
    return parser.parse_args(argv)


def amplitude_sink(products: list[ProductRow], users: list[SimUser]) -> AmplitudeSink:
    settings = get_settings()
    mapper = AmplitudeMapper(
        prices={p.id: p.price for p in products},
        traits={u.id: UserTraits(u.acquisition_source, u.signup_date, u.payment_method) for u in users},
    )
    return AmplitudeSink(settings.amplitude_api_key, mapper, server_zone=settings.amplitude_server_zone)


def snapshot_readouts(as_of: date) -> None:
    from probelens.worker.jobs import mark_run

    db = get_sessionmaker()()
    try:
        count = snapshot_experiments(db, as_of)
        db.commit()
    except Exception as exc:
        db.rollback()
        log.warning("seed_snapshots_failed", error=str(exc)[:200])
        mark_run("snapshot_experiments", False, error=str(exc)[:200])
        return
    finally:
        db.close()
    mark_run("snapshot_experiments", True, as_of=as_of, experiments=count)


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

        amplitude = None
        if get_settings().amplitude_enabled and not args.no_amplitude:
            amplitude = amplitude_sink(products, users)
        pipeline = EventPipeline([amplitude] if amplitude else [], store=ClickHouseSink(ch))
        reports = pipeline.run(sim.run(on_progress=progress))
        # Profiles are written after simulation so first_purchase_date is known.
        load_user_profiles(ch, users)
        log.info("seed_clickhouse_done", events=total_events, users=len(users))
        if amplitude:
            report = reports[-1]
            tracking_status.record_export(report, source="seed", recent=amplitude.recent())
            log.info("seed_amplitude_done", **report.as_dict())
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
        from probelens.worker.jobs import mark_run

        mark_run("detect_anomalies", True, as_of=end, **detection)
        log.info("seed_anomalies_done", **detection)
        snapshot_readouts(end)
    log.info("seed_complete", seconds=round(time.perf_counter() - started, 1), events=total_events)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
