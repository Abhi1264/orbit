from functools import lru_cache

import redis

from probelens.config import get_settings
from probelens.core.logging import get_logger

log = get_logger("redis")

@lru_cache
def get_redis() -> redis.Redis | None:
    """Redis is a cache, not a dependency: if it is unreachable the app keeps working uncached."""
    client = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=1, socket_timeout=2)
    try:
        client.ping()
    except redis.RedisError as exc:
        log.warning("redis_unavailable", error=str(exc))
        return None
    return client

def invalidate_analytics_cache() -> int:
    client = get_redis()
    if client is None:
        return 0
    deleted = 0
    for key in client.scan_iter("chq:*", count=500):
        client.delete(key)
        deleted += 1
    return deleted
