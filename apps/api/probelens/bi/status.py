from dataclasses import dataclass
from typing import Any, Literal

import httpx

from probelens.db.redis import read_json, write_json
from probelens.tracking.pipeline import describe_error

PROVISION_KEY = "orbit:integrations:metabase"


@dataclass(frozen=True)
class MetabaseProbe:
    state: Literal["connected", "needs_setup", "unreachable"]
    version: str | None = None
    detail: str | None = None


def probe(url: str, timeout: float = 3.0) -> MetabaseProbe:
    base = url.rstrip("/")
    try:
        health = httpx.get(f"{base}/api/health", timeout=timeout)
        if health.status_code != 200 or health.json().get("status") != "ok":
            return MetabaseProbe("unreachable", detail=f"Metabase is not ready (HTTP {health.status_code})")
        props = httpx.get(f"{base}/api/session/properties", timeout=timeout).json()
    except (httpx.HTTPError, ValueError) as exc:
        return MetabaseProbe("unreachable", detail=describe_error(exc))
    version = (props.get("version") or {}).get("tag")
    if not props.get("has-user-setup"):
        return MetabaseProbe("needs_setup", version, "Metabase is running but has not been set up yet")
    return MetabaseProbe("connected", version)


def record_provisioning(record: dict[str, Any]) -> None:
    write_json({PROVISION_KEY: record})


def provisioning() -> dict[str, Any] | None:
    return read_json(PROVISION_KEY)
