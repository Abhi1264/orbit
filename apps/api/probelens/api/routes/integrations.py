from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from probelens.api.deps import require
from probelens.bi import status as bi_status
from probelens.config import get_settings
from probelens.core.permissions import Permission
from probelens.db.clickhouse import get_readonly_client
from probelens.seed.simulate import EVENT_COLUMNS
from probelens.tracking import status as tracking_status
from probelens.tracking.backfill import data_range, day_batches, load_prices, load_traits
from probelens.tracking.mapping import AmplitudeMapper
from probelens.tracking.taxonomy import PLAN_BY_NAME, TRACKING_PLAN

router = APIRouter(
    prefix="/integrations", tags=["integrations"], dependencies=[Depends(require(Permission.view))]
)


class AmplitudeExport(BaseModel):
    source: str
    finished_at: datetime
    ok: bool
    rows: int
    sent: int
    delivered: int
    failed: int
    unconfirmed: int
    deferred: int
    detail: str | None


class AmplitudeStatus(BaseModel):
    status: Literal["connected", "not_configured", "invalid_key", "unreachable"]
    detail: str
    server_zone: str | None
    event_types: int
    last_export: AmplitudeExport | None


class MetabaseDashboard(BaseModel):
    name: str
    url: str | None
    cards: int


class MetabaseStatus(BaseModel):
    status: Literal["connected", "not_configured", "needs_setup", "unreachable"]
    detail: str
    version: str | None
    url: str | None
    provisioned_at: datetime | None
    dashboards: list[MetabaseDashboard]


class IntegrationsStatus(BaseModel):
    amplitude: AmplitudeStatus
    metabase: MetabaseStatus
    debugger: bool
    checked_at: datetime


def _amplitude(refresh: bool) -> AmplitudeStatus:
    settings = get_settings()
    event_types = sum(1 for spec in TRACKING_PLAN if spec.source)
    probe = tracking_status.check_api_key(refresh=refresh)
    if probe is None:
        return AmplitudeStatus(
            status="not_configured",
            detail="Not configured. Set AMPLITUDE_API_KEY to send events to Amplitude.",
            server_zone=None,
            event_types=event_types,
            last_export=None,
        )
    export = tracking_status.last_export()
    return AmplitudeStatus(
        status="connected" if probe.state == "ok" else probe.state,
        detail=probe.detail or "Amplitude accepted the API key.",
        server_zone=settings.amplitude_server_zone,
        event_types=event_types,
        last_export=AmplitudeExport(**{k: export.get(k) for k in AmplitudeExport.model_fields})
        if export
        else None,
    )


def _metabase() -> MetabaseStatus:
    settings = get_settings()
    site = settings.metabase_site_url.rstrip("/") or None
    if not settings.metabase_url:
        return MetabaseStatus(
            status="not_configured",
            detail="Not configured. Set METABASE_URL and run `make bi` to start Metabase "
            "with Orbit's dashboards.",
            version=None,
            url=None,
            provisioned_at=None,
            dashboards=[],
        )
    probe = bi_status.probe(settings.metabase_url)
    record = bi_status.provisioning() if probe.state == "connected" else None
    if probe.state == "connected":
        detail = (
            "Connected. Dashboards read ClickHouse and Postgres through read-only users."
            if record
            else "Connected, but Orbit's dashboards have not been provisioned. Run `make bi-setup`."
        )
    else:
        detail = probe.detail or ""
    return MetabaseStatus(
        status=probe.state,
        detail=detail,
        version=probe.version,
        url=site if probe.state != "unreachable" else None,
        provisioned_at=record.get("provisioned_at") if record else None,
        dashboards=[
            MetabaseDashboard(
                name=d["name"], url=f"{site}/dashboard/{d['id']}" if site else None, cards=d["cards"]
            )
            for d in (record or {}).get("dashboards", [])
        ],
    )


@router.get("", response_model=IntegrationsStatus)
def integrations_status(refresh: bool = False) -> IntegrationsStatus:
    return IntegrationsStatus(
        amplitude=_amplitude(refresh),
        metabase=_metabase(),
        debugger=not get_settings().is_production,
        checked_at=datetime.now(UTC),
    )


AmplitudeDelivery = Literal["delivered", "failed", "pending", "not_configured", "unknown"]
_USER_ID = EVENT_COLUMNS.index("user_id")


class DebugEvent(BaseModel):
    event_type: str
    orbit_event: str | None
    user_id: str
    time: datetime
    insert_id: str
    session_id: int | None
    platform: str | None
    event_properties: dict[str, Any]
    user_properties: dict[str, Any]
    revenue: float | None
    clickhouse: Literal["stored"]
    amplitude: AmplitudeDelivery


class DebugEvents(BaseModel):
    source: Literal["last_export", "clickhouse_preview", "empty"]
    amplitude_configured: bool
    events: list[DebugEvent]


def _development_only() -> None:
    if get_settings().is_production:
        raise HTTPException(status_code=404, detail="Not Found")


def _debug_event(event: dict[str, Any], amplitude: AmplitudeDelivery) -> DebugEvent:
    spec = PLAN_BY_NAME.get(event["event_type"])
    session_id = event.get("session_id")
    return DebugEvent(
        event_type=event["event_type"],
        orbit_event=spec.source if spec else None,
        user_id=event["user_id"],
        time=datetime.fromtimestamp(event["time"] / 1000, UTC),
        insert_id=event["insert_id"],
        session_id=session_id if session_id is not None and session_id >= 0 else None,
        platform=event.get("platform"),
        event_properties=event.get("event_properties") or {},
        user_properties=event.get("user_properties") or {},
        revenue=event.get("revenue"),
        clickhouse="stored",
        amplitude=amplitude,
    )


def _preview(limit: int) -> list[dict[str, Any]]:
    ch = get_readonly_client()
    span = data_range(ch)
    if span is None:
        return []
    rows = next(day_batches(ch, span[1], span[1]))
    if not rows:
        return []
    user_ids = sorted({row[_USER_ID] for row in rows})
    events = AmplitudeMapper(load_prices(), load_traits(ch, user_ids)).map(rows)
    return [e.to_dict() for e in sorted(events, key=lambda e: e.time)[-limit:]]


@router.get("/debug/events", response_model=DebugEvents, dependencies=[Depends(_development_only)])
def debug_events(limit: int = Query(default=25, ge=1, le=50)) -> DebugEvents:
    configured = get_settings().amplitude_enabled
    recent = tracking_status.recent_events()
    if recent:
        events = [_debug_event(e, e.get("amplitude", "unknown")) for e in reversed(recent[-limit:])]
        return DebugEvents(source="last_export", amplitude_configured=configured, events=events)
    preview = _preview(limit)
    delivery: AmplitudeDelivery = "unknown" if configured else "not_configured"
    return DebugEvents(
        source="clickhouse_preview" if preview else "empty",
        amplitude_configured=configured,
        events=[_debug_event(e, delivery) for e in reversed(preview)],
    )
