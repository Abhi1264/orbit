from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from probelens.config import get_settings
from probelens.db.redis import read_json, write_json
from probelens.tracking.amplitude import BATCH_URLS, ProbeResult, probe_api_key
from probelens.tracking.pipeline import SinkReport

LAST_EXPORT_KEY = "orbit:integrations:amplitude:last_export"
RECENT_EVENTS_KEY = "orbit:integrations:amplitude:recent"
PROBE_KEY = "orbit:integrations:amplitude:probe:{}"
PROBE_TTL_SECONDS = {"ok": 600, "invalid_key": 600, "unreachable": 60}


def record_export(report: SinkReport, source: str, recent: list[dict[str, Any]]) -> None:
    summary = {**report.as_dict(), "source": source, "finished_at": datetime.now(UTC).isoformat()}
    write_json({LAST_EXPORT_KEY: summary, RECENT_EVENTS_KEY: recent})


def last_export() -> dict[str, Any] | None:
    return read_json(LAST_EXPORT_KEY)


def recent_events() -> list[dict[str, Any]]:
    return read_json(RECENT_EVENTS_KEY) or []


def check_api_key(refresh: bool = False) -> ProbeResult | None:
    settings = get_settings()
    if not settings.amplitude_api_key:
        return None
    fingerprint = hashlib.sha256(
        f"{settings.amplitude_server_zone}:{settings.amplitude_api_key}".encode()
    ).hexdigest()[:16]
    cache_key = PROBE_KEY.format(fingerprint)
    if not refresh and (cached := read_json(cache_key)):
        return ProbeResult(**cached)
    result = probe_api_key(settings.amplitude_api_key, BATCH_URLS[settings.amplitude_server_zone])
    write_json({cache_key: asdict(result)}, ttl_seconds=PROBE_TTL_SECONDS[result.state])
    return result
