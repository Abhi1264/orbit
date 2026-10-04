from __future__ import annotations

import json
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from fastapi import HTTPException

from probelens.api.routes import integrations
from probelens.bi import status as bi_status
from probelens.bi.status import MetabaseProbe
from probelens.config import Settings
from probelens.tracking import status as tracking_status
from probelens.tracking.amplitude import ProbeResult
from probelens.tracking.taxonomy import PLAN_BY_NAME

API_KEY = "0123456789abcdef0123456789abcdef"
RECORD = {
    "provisioned_at": "2026-10-04T18:00:00+00:00",
    "dashboards": [{"id": 3, "name": "Orbit · Product overview", "cards": 14}],
}


@pytest.fixture
def configure(monkeypatch: pytest.MonkeyPatch):
    def apply(**overrides: Any) -> Settings:
        settings = Settings(
            **{"amplitude_api_key": "", "metabase_url": "", "metabase_site_url": "", **overrides}
        )
        for module in (integrations, tracking_status):
            monkeypatch.setattr(module, "get_settings", lambda: settings)
        return settings

    return apply


def test_unconfigured_integrations_say_not_configured(configure) -> None:
    configure()
    status = integrations.integrations_status()
    assert status.amplitude.status == "not_configured"
    assert status.amplitude.detail.startswith("Not configured.")
    assert status.amplitude.last_export is None
    assert status.metabase.status == "not_configured"
    assert status.metabase.detail.startswith("Not configured.")
    assert status.metabase.url is None and status.metabase.dashboards == []
    assert status.debugger is True


def test_amplitude_status_is_the_live_check_and_never_includes_the_key(configure, monkeypatch) -> None:
    configure(amplitude_api_key=API_KEY, amplitude_server_zone="EU")
    for state, expected in [
        ("ok", "connected"),
        ("invalid_key", "invalid_key"),
        ("unreachable", "unreachable"),
    ]:
        probe = ProbeResult(state, "" if state == "ok" else f"Amplitude said {state}")
        monkeypatch.setattr(tracking_status, "check_api_key", lambda refresh=False, p=probe: p)
        monkeypatch.setattr(tracking_status, "last_export", lambda: None)
        status = integrations._amplitude(refresh=False)
        assert status.status == expected
        assert status.server_zone == "EU"
        assert API_KEY not in status.model_dump_json()


def test_metabase_connected_without_dashboards_asks_for_provisioning(configure, monkeypatch) -> None:
    configure(metabase_url="http://metabase:3000", metabase_site_url="http://bi.example")
    monkeypatch.setattr(bi_status, "probe", lambda url: MetabaseProbe("connected", "v0.63.18.1"))
    monkeypatch.setattr(bi_status, "provisioning", lambda: None)
    status = integrations._metabase()
    assert status.status == "connected"
    assert "make bi-setup" in status.detail
    assert status.dashboards == [] and status.url == "http://bi.example"


def test_metabase_dashboard_links_use_the_browser_facing_url(configure, monkeypatch) -> None:
    configure(metabase_url="http://metabase:3000", metabase_site_url="http://bi.example/")
    monkeypatch.setattr(bi_status, "probe", lambda url: MetabaseProbe("connected", "v0.63.18.1"))
    monkeypatch.setattr(bi_status, "provisioning", lambda: RECORD)
    status = integrations._metabase()
    assert status.version == "v0.63.18.1"
    assert [(d.name, d.url, d.cards) for d in status.dashboards] == [
        ("Orbit · Product overview", "http://bi.example/dashboard/3", 14)
    ]


def test_unreachable_metabase_is_reported_without_links(configure, monkeypatch) -> None:
    configure(metabase_url="http://metabase:3000", metabase_site_url="http://bi.example")
    monkeypatch.setattr(
        bi_status, "probe", lambda url: MetabaseProbe("unreachable", detail="Connection refused")
    )
    monkeypatch.setattr(bi_status, "provisioning", lambda: RECORD)
    status = integrations._metabase()
    assert status.status == "unreachable" and status.detail == "Connection refused"
    assert status.url is None and status.dashboards == []


def test_debugger_is_hidden_in_production(configure) -> None:
    configure(app_env="production")
    assert integrations.integrations_status().debugger is False
    with pytest.raises(HTTPException) as exc:
        integrations._development_only()
    assert exc.value.status_code == 404


@contextmanager
def stub_metabase(routes: dict[str, tuple[int, dict]]) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            status, payload = routes.get(self.path, (404, {}))
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


HEALTHY = (200, {"status": "ok"})


def test_probe_reports_connected_with_the_version() -> None:
    props = (200, {"has-user-setup": True, "version": {"tag": "v0.63.18.1"}})
    with stub_metabase({"/api/health": HEALTHY, "/api/session/properties": props}) as url:
        assert bi_status.probe(url + "/") == MetabaseProbe("connected", "v0.63.18.1")


def test_probe_reports_needs_setup_before_the_first_run() -> None:
    props = (200, {"has-user-setup": False, "version": {"tag": "v0.63.18.1"}})
    with stub_metabase({"/api/health": HEALTHY, "/api/session/properties": props}) as url:
        result = bi_status.probe(url)
    assert result.state == "needs_setup" and result.version == "v0.63.18.1"


def test_probe_reports_unreachable_when_starting_or_down() -> None:
    with stub_metabase({"/api/health": (503, {"status": "initializing"})}) as url:
        starting = bi_status.probe(url)
    assert starting.state == "unreachable" and "HTTP 503" in (starting.detail or "")

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    down = bi_status.probe(f"http://127.0.0.1:{port}", timeout=1.0)
    assert down.state == "unreachable" and down.detail


def test_integrations_endpoint_reports_real_states(api_client) -> None:
    res = api_client.get("/api/integrations")
    assert res.status_code == 200
    body = res.json()
    assert body["amplitude"]["status"] in {"connected", "not_configured", "invalid_key", "unreachable"}
    assert body["metabase"]["status"] in {"connected", "not_configured", "needs_setup", "unreachable"}
    assert body["amplitude"]["event_types"] == sum(1 for spec in PLAN_BY_NAME.values() if spec.source)


def test_debugger_previews_stored_events_through_the_plan(api_client) -> None:
    res = api_client.get("/api/integrations/debug/events", params={"limit": 5})
    assert res.status_code == 200
    body = res.json()
    assert body["source"] in {"last_export", "clickhouse_preview"}
    assert 0 < len(body["events"]) <= 5
    for event in body["events"]:
        assert event["event_type"] in PLAN_BY_NAME
        assert event["clickhouse"] == "stored"
        assert event["amplitude"] in {"delivered", "failed", "pending", "not_configured", "unknown"}
