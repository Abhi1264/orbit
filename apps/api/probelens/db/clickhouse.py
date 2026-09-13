import hashlib
import json
import time
from functools import lru_cache
from typing import Any

import clickhouse_connect
import clickhouse_connect.driver.httputil
from clickhouse_connect.driver.client import Client

from probelens.config import get_settings
from probelens.core.logging import get_logger
from probelens.db.redis import get_redis

log = get_logger("clickhouse")

SLOW_QUERY_MS = 500

def _new_client(user: str, password: str) -> Client:
    settings = get_settings()
    return clickhouse_connect.get_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        database=settings.clickhouse_database,
        username=user,
        password=password,
        compress=True,
        # Requests run in FastAPI's threadpool and share this client. Without a
        # session id ClickHouse treats each query independently, which is what
        # we want: the analytics path never uses session state (temp tables etc.).
        autogenerate_session_id=False,
        pool_mgr=clickhouse_connect.driver.httputil.get_pool_manager(maxsize=32, num_pools=4),
    )

@lru_cache
def get_readonly_client() -> Client:
    settings = get_settings()
    return _new_client(settings.clickhouse_readonly_user, settings.clickhouse_readonly_password)

@lru_cache
def get_readwrite_client() -> Client:
    settings = get_settings()
    return _new_client(settings.clickhouse_user, settings.clickhouse_password)

class AnalyticsQueryError(RuntimeError):
    pass

def _cache_key(sql: str, params: dict[str, Any]) -> str:
    payload = json.dumps({"sql": sql, "params": params}, sort_keys=True, default=str)
    return "chq:" + hashlib.sha256(payload.encode()).hexdigest()

def run_query(
    sql: str,
    params: dict[str, Any] | None = None,
    *,
    cache: bool = True,
    label: str = "query",
) -> list[dict[str, Any]]:
    """Execute a read-only analytical query, returning rows as dicts.

    All values are bound server-side through clickhouse-connect parameters, so
    callers never interpolate user input into SQL. Results are cached in Redis
    keyed by the exact SQL + parameters; the demo dataset is static, so a short
    TTL makes repeated dashboard loads cheap.
    """
    params = params or {}
    settings = get_settings()
    redis = get_redis()
    key = _cache_key(sql, params)

    if cache and redis is not None:
        cached = redis.get(key)
        if cached:
            return json.loads(cached)

    started = time.perf_counter()
    try:
        result = get_readonly_client().query(sql, parameters=params)
    except Exception as exc:  # clickhouse-connect raises several error types
        log.error("clickhouse_query_failed", label=label, error=str(exc)[:500])
        raise AnalyticsQueryError(str(exc)) from exc
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    rows = [dict(zip(result.column_names, row, strict=True)) for row in result.result_rows]
    log_fn = log.warning if elapsed_ms > SLOW_QUERY_MS else log.debug
    log_fn(
        "clickhouse_query",
        label=label,
        ms=elapsed_ms,
        rows=len(rows),
        read_rows=result.summary.get("read_rows"),
    )

    if cache and redis is not None:
        redis.setex(key, settings.analytics_cache_ttl_seconds, json.dumps(rows, default=str))
    return rows
