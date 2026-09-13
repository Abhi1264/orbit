"""Fixed-window rate limiter for abuse-prone endpoints (login).

Uses Redis when available so limits hold across API replicas; falls back to a
process-local dict so a missing cache never disables the protection entirely.
"""

from __future__ import annotations

import contextlib
import threading
import time

from probelens.db.redis import get_redis

_local: dict[str, tuple[int, float]] = {}
_lock = threading.Lock()

def hit(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Record one attempt; return (allowed, seconds until the window resets)."""
    redis = get_redis()
    if redis is not None:
        try:
            pipe = redis.pipeline()
            pipe.incr(f"rl:{key}")
            pipe.ttl(f"rl:{key}")
            count, ttl = pipe.execute()
            if ttl is None or ttl < 0:
                redis.expire(f"rl:{key}", window_seconds)
                ttl = window_seconds
            return count <= limit, int(ttl)
        except Exception:
            pass
    now = time.monotonic()
    with _lock:
        count, reset_at = _local.get(key, (0, now + window_seconds))
        if now >= reset_at:
            count, reset_at = 0, now + window_seconds
        count += 1
        _local[key] = (count, reset_at)
        if len(_local) > 10_000:  # bounded memory under a flood
            for k in [k for k, (_, r) in _local.items() if r < now][:5_000]:
                _local.pop(k, None)
    return count <= limit, int(reset_at - now) + 1

def reset(key: str) -> None:
    redis = get_redis()
    if redis is not None:
        with contextlib.suppress(Exception):
            redis.delete(f"rl:{key}")
    with _lock:
        _local.pop(key, None)
