from __future__ import annotations

import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from amplitude import Amplitude, BaseEvent, Config

from probelens.core.logging import get_logger
from probelens.tracking.mapping import AmplitudeEvent, AmplitudeMapper
from probelens.tracking.pipeline import SinkReport

log = get_logger("tracking.amplitude")

BATCH_URLS = {"US": "https://api2.amplitude.com/batch", "EU": "https://api.eu.amplitude.com/batch"}
RECENT_LIMIT = 50


@dataclass(frozen=True)
class ProbeResult:
    state: Literal["ok", "invalid_key", "unreachable"]
    detail: str = ""


def probe_api_key(api_key: str, url: str, timeout: float = 5.0) -> ProbeResult:
    # Amplitude validates the key before the payload, so an empty upload checks the key and sends nothing.
    try:
        resp = httpx.post(url, json={"api_key": api_key, "events": []}, timeout=timeout)
    except httpx.HTTPError as exc:
        return ProbeResult("unreachable", f"Could not reach Amplitude ({type(exc).__name__})")
    if resp.status_code == 400 and "invalid api key" in resp.text.lower():
        return ProbeResult("invalid_key", "Amplitude rejected the API key")
    if resp.status_code in (200, 400):
        return ProbeResult("ok")
    return ProbeResult("unreachable", f"Amplitude returned HTTP {resp.status_code}")


class AmplitudeSink:
    name = "amplitude"

    def __init__(
        self,
        api_key: str,
        mapper: AmplitudeMapper,
        *,
        server_zone: str = "US",
        server_url: str | None = None,
        flush_size: int = 1000,
        stall_seconds: float = 60.0,
        max_empty_batches: int = 2,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._api_key = api_key
        self._mapper = mapper
        self._stall_seconds = stall_seconds
        self._max_empty_batches = max_empty_batches
        self._clock = clock
        self._cond = threading.Condition()
        self._rows = self._sent = self._delivered = self._failed = self._lost = 0
        self._deferred = self._skipped = self._empty_batches = 0
        self._reasons: Counter[str] = Counter()
        self._recent: list[AmplitudeEvent] = []
        self._recent_status: dict[str, str] = {}
        self._stopped: str | None = None
        self._client: Amplitude | None = None

        url = server_url or BATCH_URLS[server_zone]
        probe = probe_api_key(api_key, url)
        if probe.state != "ok":
            self._stop(f"Nothing sent: {probe.detail}")
            return
        self._client = Amplitude(
            api_key,
            Config(
                server_url=url,
                use_batch=True,
                flush_queue_size=flush_size,
                flush_interval_millis=1000,
                flush_max_retries=3,
                min_id_length=1,  # Orbit user ids are short integers
                callback=self._on_result,
            ),
        )

    def write(self, rows: list[tuple]) -> None:
        self._rows += len(rows)
        if self._client is None or self._stopped:
            self._skipped += len(rows)
            return
        events = self._mapper.map(rows)
        now_ms = int(self._clock() * 1000)
        ready = [e for e in events if e.time <= now_ms]
        self._deferred += len(events) - len(ready)
        if not ready:
            return
        with self._cond:
            self._recent = ready[-RECENT_LIMIT:]
            self._recent_status = {e.insert_id: "pending" for e in self._recent}
            delivered_before = self._delivered
        for event in ready:
            self._client.track(BaseEvent(**event.to_dict()))
        with self._cond:
            self._sent += len(ready)
        self._client.flush()
        self._await_outcomes(delivered_before)

    def close(self) -> SinkReport:
        if self._client is not None:
            self._client.shutdown()
            self._client = None
        with self._cond:
            unconfirmed = max(0, self._sent - self._delivered - self._failed)
            detail = self._stopped or "; ".join(f"{r} ({n})" for r, n in self._reasons.most_common(3))
            return SinkReport(
                self.name,
                ok=not self._stopped and self._failed == 0 and unconfirmed == 0,
                rows=self._rows,
                sent=self._sent,
                delivered=self._delivered,
                failed=self._failed,
                unconfirmed=unconfirmed,
                deferred=self._deferred,
                skipped=self._skipped,
                detail=detail,
            )

    def recent(self) -> list[dict[str, Any]]:
        with self._cond:
            return [
                {**e.to_dict(), "amplitude": self._recent_status.get(e.insert_id, "pending")}
                for e in self._recent
            ]

    def _on_result(self, event: BaseEvent, code: int, message: str | None) -> None:
        with self._cond:
            if code == 200:
                self._delivered += 1
                status = "delivered"
            else:
                self._failed += 1
                reason = f"HTTP {code}: {message}" if message else f"HTTP {code}"
                self._reasons[reason.replace(self._api_key, "[redacted]")[:160]] += 1
                status = "failed"
            if event.insert_id in self._recent_status:
                self._recent_status[event.insert_id] = status
            self._cond.notify_all()

    def _await_outcomes(self, delivered_before: int) -> None:
        with self._cond:
            while self._delivered + self._failed + self._lost < self._sent:
                if not self._cond.wait(timeout=self._stall_seconds):
                    self._lost = self._sent - self._delivered - self._failed
                    break
            delivered = self._delivered - delivered_before
            stalled = self._delivered + self._failed < self._sent
            top_reason = self._reasons.most_common(1)[0][0] if self._reasons else ""
        if delivered:
            self._empty_batches = 0
            return
        self._empty_batches += 1
        if self._empty_batches >= self._max_empty_batches:
            if stalled:
                self._stop(f"Stopped sending: no response from Amplitude for {self._stall_seconds:g}s")
            else:
                self._stop(f"Stopped sending: Amplitude rejected every event ({top_reason})")

    def _stop(self, reason: str) -> None:
        self._stopped = reason
        log.warning("amplitude_sink_stopped", reason=reason)
