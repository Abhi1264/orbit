"""Product labels for breakdowns, read from Postgres and cached in-process."""

import time

from sqlalchemy import select

from probelens.db.postgres import get_sessionmaker
from probelens.models import Product

_cache: dict[str, str] = {}
_cache_at = 0.0
_TTL = 600


def product_labels() -> dict[str, str]:
    global _cache, _cache_at
    if _cache and time.monotonic() - _cache_at < _TTL:
        return _cache
    with get_sessionmaker()() as db:
        rows = db.execute(select(Product.id, Product.name)).all()
    _cache = {str(pid): name for pid, name in rows}
    _cache_at = time.monotonic()
    return _cache
