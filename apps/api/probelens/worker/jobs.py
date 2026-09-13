"""Background jobs. Dramatiq actors run on the worker; APScheduler enqueues the
periodic ones. Everything here is idempotent so a retry never double-writes."""

from datetime import UTC, date, datetime

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from probelens.analytics.anomalies import run_detection
from probelens.analytics.meta import get_meta
from probelens.config import get_settings
from probelens.core.logging import get_logger
from probelens.db.postgres import get_sessionmaker
from probelens.db.redis import invalidate_analytics_cache
from probelens.services.projects import default_project_id

log = get_logger("worker")

broker = RedisBroker(url=get_settings().redis_url)
dramatiq.set_broker(broker)


@dramatiq.actor(max_retries=2, time_limit=5 * 60 * 1000)
def detect_anomalies(as_of_iso: str | None = None) -> None:
    """Sweep every monitored series and upsert anomaly windows.

    Anchored to the dataset's last day rather than the wall clock so the demo
    dataset keeps producing the same anomalies however long it sits.
    """
    db = get_sessionmaker()()
    try:
        as_of = date.fromisoformat(as_of_iso) if as_of_iso else (get_meta().data_end or date.today())
        summary = run_detection(db, default_project_id(db), as_of, datetime.now(UTC))
        db.commit()
        log.info("job_detect_anomalies_done", as_of=str(as_of), **summary)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@dramatiq.actor(max_retries=0)
def refresh_analytics_cache() -> None:
    """Drop cached ClickHouse results so dashboards pick up newly loaded data."""
    deleted = invalidate_analytics_cache()
    log.info("job_cache_invalidated", keys=deleted)
