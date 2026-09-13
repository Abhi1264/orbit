"""Operational status for the Settings → System panel and for smoke checks in CI."""

from __future__ import annotations

import time
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, text

from probelens.api.deps import CurrentUser, DbSession, require
from probelens.config import get_settings
from probelens.core.permissions import Permission
from probelens.db.clickhouse import get_readonly_client
from probelens.db.redis import get_redis
from probelens.models import (
    AiRun,
    Anomaly,
    Decision,
    Experiment,
    Feedback,
    Investigation,
    KnowledgeDocument,
    Release,
    Sop,
    User,
)

router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(require(Permission.view))])


class Dependency(BaseModel):
    name: str
    ok: bool
    latency_ms: float | None
    detail: str


class JobRun(BaseModel):
    job: str
    at: datetime | None
    ok: bool | None
    detail: dict[str, str]


class DataStatus(BaseModel):
    data_start: date | None
    data_end: date | None
    events: int
    users: int
    cache_keys: int


class SystemStatus(BaseModel):
    env: str
    version: str
    llm_mode: str
    llm_model: str | None
    dependencies: list[Dependency]
    worker_heartbeat: datetime | None
    worker_alive: bool
    jobs: list[JobRun]
    data: DataStatus
    counts: dict[str, int]
    last_anomaly_detection: datetime | None
    ai_runs_24h: int
    ai_errors_24h: int
    generated_at: datetime


def _probe(name: str, fn) -> Dependency:
    started = time.perf_counter()
    try:
        detail = fn()
        return Dependency(
            name=name, ok=True, latency_ms=round((time.perf_counter() - started) * 1000, 1), detail=detail
        )
    except Exception as exc:
        return Dependency(name=name, ok=False, latency_ms=None, detail=str(exc)[:200])


@router.get("/status", response_model=SystemStatus)
def system_status(_: CurrentUser, db: DbSession) -> SystemStatus:
    settings = get_settings()

    def pg() -> str:
        return str(db.execute(text("select version()")).scalar()).split(" on ")[0][:60]

    def ch() -> str:
        return f"ClickHouse {get_readonly_client().command('select version()')}"

    def rd() -> str:
        client = get_redis()
        if client is None:
            raise RuntimeError("unreachable")
        info = client.info("memory")
        return f"used {int(info.get('used_memory', 0)) // 1024 // 1024} MB"

    deps = [_probe("postgres", pg), _probe("clickhouse", ch), _probe("redis", rd)]

    events = users = 0
    data_start = data_end = None
    try:
        client = get_readonly_client()
        row = client.query(
            f"SELECT count(), uniqExact(user_id), min(event_date), max(event_date) "
            f"FROM {settings.clickhouse_database}.events"
        ).result_rows[0]
        events, users = int(row[0]), int(row[1])
        data_start, data_end = (row[2], row[3]) if events else (None, None)
    except Exception:
        pass

    cache_keys = 0
    heartbeat: datetime | None = None
    jobs: list[JobRun] = []
    redis = get_redis()
    if redis is not None:
        try:
            cache_keys = sum(1 for _ in redis.scan_iter("chq:*", count=1000))
            hb = redis.get("orbit:worker:heartbeat")
            heartbeat = datetime.fromisoformat(hb.decode()) if hb else None
            for job in ("detect_anomalies", "refresh_analytics_cache"):
                raw = redis.hgetall(f"orbit:worker:last_run:{job}")
                data = {k.decode(): v.decode() for k, v in raw.items()}
                at = data.pop("at", None)
                ok = data.pop("ok", None)
                jobs.append(
                    JobRun(
                        job=job,
                        at=datetime.fromisoformat(at) if at else None,
                        ok=None if ok is None else ok == "True",
                        detail=data,
                    )
                )
        except Exception:
            pass

    now = datetime.now(UTC)
    counts = {
        name: int(db.scalar(select(func.count()).select_from(model)) or 0)
        for name, model in (
            ("users", User),
            ("investigations", Investigation),
            ("anomalies", Anomaly),
            ("experiments", Experiment),
            ("releases", Release),
            ("decisions", Decision),
            ("sops", Sop),
            ("knowledge", KnowledgeDocument),
            ("feedback", Feedback),
            ("ai_runs", AiRun),
        )
    }
    since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    ai_runs_24h = int(db.scalar(select(func.count()).where(AiRun.created_at >= since)) or 0)
    ai_errors_24h = int(
        db.scalar(select(func.count()).where(AiRun.created_at >= since, AiRun.error != "")) or 0
    )

    return SystemStatus(
        env=settings.app_env,
        version="0.1.0",
        llm_mode="llm" if settings.llm_enabled else "demo",
        llm_model=settings.llm_model if settings.llm_enabled else None,
        dependencies=deps,
        worker_heartbeat=heartbeat,
        worker_alive=heartbeat is not None and (now - heartbeat).total_seconds() < 180,
        jobs=jobs,
        data=DataStatus(
            data_start=data_start,
            data_end=data_end,
            events=events,
            users=users,
            cache_keys=cache_keys,
        ),
        counts=counts,
        last_anomaly_detection=db.scalar(select(func.max(Anomaly.detected_at))),
        ai_runs_24h=ai_runs_24h,
        ai_errors_24h=ai_errors_24h,
        generated_at=now,
    )
