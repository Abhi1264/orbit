import json
from functools import lru_cache
from typing import Any

import redis

from probelens.config import get_settings
from probelens.core.logging import get_logger

log = get_logger("redis")


@lru_cache
def get_redis() -> redis.Redis | None:
    client = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=1, socket_timeout=2)
    try:
        client.ping()
    except redis.RedisError as exc:
        log.warning("redis_unavailable", error=str(exc))
        return None
    return client


def read_json(key: str) -> Any:
    client = get_redis()
    if client is None:
        return None
    try:
        raw = client.get(key)
    except redis.RedisError as exc:
        log.warning("redis_read_failed", key=key, error=str(exc))
        return None
    return json.loads(raw) if raw else None


def write_json(values: dict[str, Any], ttl_seconds: int | None = None) -> bool:
    client = get_redis()
    if client is None:
        return False
    try:
        pipe = client.pipeline()
        for key, value in values.items():
            pipe.set(key, json.dumps(value), ex=ttl_seconds)
        pipe.execute()
    except redis.RedisError as exc:
        log.warning("redis_write_failed", keys=list(values), error=str(exc))
        return False
    return True


def invalidate_analytics_cache() -> int:
    client = get_redis()
    if client is None:
        return 0
    deleted = 0
    for key in client.scan_iter("chq:*", count=500):
        client.delete(key)
        deleted += 1
    return deleted
