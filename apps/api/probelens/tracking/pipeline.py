from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from probelens.config import get_settings
from probelens.core.logging import get_logger

log = get_logger("tracking")


@dataclass
class SinkReport:
    name: str
    ok: bool
    rows: int = 0  # storefront rows received
    sent: int = 0  # destination events submitted
    delivered: int = 0  # confirmed by the destination
    failed: int = 0  # rejected, or given up on after retries
    unconfirmed: int = 0  # no outcome before the sink stopped waiting
    deferred: int = 0  # stamped later than now; a later backfill sends them
    skipped: int = 0  # rows not sent because the sink had stopped
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class EventStore(Protocol):
    name: str

    def write(self, rows: list[tuple]) -> list[list[tuple]]: ...

    def flush(self) -> list[list[tuple]]: ...

    def report(self) -> SinkReport: ...


class Sink(Protocol):
    name: str

    def write(self, rows: list[tuple]) -> None: ...

    def close(self) -> SinkReport: ...


def describe_error(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"[:300]
    return redact(text)


def redact(text: str) -> str:
    # Amplitude echoes a rejected key back in its error message.
    key = get_settings().amplitude_api_key
    return text.replace(key, "[redacted]") if key else text


class EventPipeline:
    def __init__(self, sinks: Sequence[Sink], store: EventStore | None = None) -> None:
        self.store = store
        self.sinks = list(sinks)
        self._errors: dict[str, str] = {}

    def run(self, batches: Iterable[list[tuple]]) -> list[SinkReport]:
        try:
            for rows in batches:
                self.write(rows)
        except BaseException:
            self._close_sinks()
            raise
        return self.close()

    def write(self, rows: list[tuple]) -> None:
        committed = self.store.write(rows) if self.store else [rows]
        self._forward(committed)

    def close(self) -> list[SinkReport]:
        reports = []
        if self.store:
            self._forward(self.store.flush())
            reports.append(self.store.report())
        return reports + self._close_sinks()

    def _forward(self, batches: list[list[tuple]]) -> None:
        for sink in self.sinks:
            if sink.name in self._errors:
                continue
            try:
                for rows in batches:
                    sink.write(rows)
            except Exception as exc:
                self._errors[sink.name] = describe_error(exc)
                log.warning("tracking_sink_detached", sink=sink.name, error=self._errors[sink.name])

    def _close_sinks(self) -> list[SinkReport]:
        reports = []
        for sink in self.sinks:
            try:
                report = sink.close()
            except Exception as exc:
                report = SinkReport(sink.name, ok=False, detail=describe_error(exc))
                log.warning("tracking_sink_close_failed", sink=sink.name, error=report.detail)
            if sink.name in self._errors:
                report.ok = False
                report.detail = self._errors[sink.name]
            reports.append(report)
        return reports
