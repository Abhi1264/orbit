from datetime import UTC, date, datetime

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from probelens.analytics.anomalies import run_detection
from probelens.analytics.meta import get_meta
from probelens.config import get_settings
from probelens.core.logging import get_logger
from probelens.db.postgres import get_sessionmaker
from probelens.db.redis import get_redis
from probelens.experiments import snapshots
from probelens.services.projects import default_project_id

log = get_logger("worker")

HEARTBEAT_KEY = "orbit:worker:heartbeat"
LAST_RUN_KEY = "orbit:worker:last_run:{job}"


def mark_run(job: str, ok: bool, **fields: object) -> None:
    redis = get_redis()
    if redis is None:
        return
    payload = {
        "at": datetime.now(UTC).isoformat(),
        "ok": str(ok),
        **{k: str(v) for k, v in fields.items()},
    }
    redis.hset(LAST_RUN_KEY.format(job=job), mapping=payload)


def heartbeat() -> None:
    redis = get_redis()
    if redis is not None:
        redis.set(HEARTBEAT_KEY, datetime.now(UTC).isoformat(), ex=180)


broker = RedisBroker(url=get_settings().redis_url)
dramatiq.set_broker(broker)


@dramatiq.actor(max_retries=2, time_limit=5 * 60 * 1000)
def detect_anomalies(as_of_iso: str | None = None) -> None:
    db = get_sessionmaker()()
    try:
        as_of = date.fromisoformat(as_of_iso) if as_of_iso else (get_meta().data_end or date.today())
        summary = run_detection(db, default_project_id(db), as_of, datetime.now(UTC))
        db.commit()
        log.info("job_detect_anomalies_done", as_of=str(as_of), **summary)
        mark_run("detect_anomalies", True, as_of=as_of, **summary)
    except Exception as exc:
        db.rollback()
        mark_run("detect_anomalies", False, error=str(exc)[:200])
        raise
    finally:
        db.close()


@dramatiq.actor(max_retries=2, time_limit=5 * 60 * 1000)
def snapshot_experiments(as_of_iso: str | None = None) -> None:
    db = get_sessionmaker()()
    try:
        as_of = date.fromisoformat(as_of_iso) if as_of_iso else (get_meta().data_end or date.today())
        count = snapshots.snapshot_experiments(db, as_of)
        db.commit()
        log.info("job_snapshot_experiments_done", as_of=str(as_of), experiments=count)
        mark_run("snapshot_experiments", True, as_of=as_of, experiments=count)
    except Exception as exc:
        db.rollback()
        mark_run("snapshot_experiments", False, error=str(exc)[:200])
        raise
    finally:
        db.close()
