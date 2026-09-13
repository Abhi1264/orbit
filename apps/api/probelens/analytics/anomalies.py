"""Anomaly detection over daily metric series.

The detector is deliberately simple and explainable: for every monitored series
it compares each day in the detection window against a trailing baseline using
a robust z-score (median / MAD, so a single bad day does not inflate the
baseline's spread) with a weekday adjustment for volume metrics. Consecutive
flagged days are merged into one anomaly window so a four-day regression shows
up once, not four times.

Detection is anchored to `as_of` (the dataset's last day), not the wall clock,
so the demo dataset produces the same anomalies wherever it is run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from math import sqrt
from statistics import median
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from probelens.analytics.dimensions import DIMENSIONS, Filter
from probelens.analytics.metrics import get_metric
from probelens.analytics.query import MetricQuery, Point, run_metric_query
from probelens.core.logging import get_logger
from probelens.models import Anomaly

log = get_logger("anomalies")

BASELINE_DAYS = 28  # clean (unflagged) days used as the baseline
BASELINE_LOOKBACK_DAYS = 56  # how far back to look for those clean days
DETECTION_WINDOW_DAYS = 42  # anomalies ending before this are considered history
Z_THRESHOLD = 3.0
# A day right after a flagged one stays in the window (and out of the baseline) at a
# lower bar: regressions do not politely clear the threshold every single day, and
# letting those days back into the baseline is how it drifts toward the new level.
CONTINUATION_Z = 2.0
# One-day windows are mostly noise on ratio metrics; they only surface when extreme.
SINGLE_DAY_Z = 4.5
MIN_RELATIVE_CHANGE = 0.05
MIN_BASELINE_POINTS = 14
# Ignore series whose denominator is too small for a stable rate.
MIN_DAILY_DENOMINATOR = 60
MIN_ROLLING_DENOMINATOR = 200


@dataclass(frozen=True)
class Monitor:
    metric: str
    breakdown: str | None = None
    filters: tuple[Filter, ...] = ()
    limit: int = 10
    # Low-volume ratio metrics are scored on a trailing window instead of single
    # days; a 7-day window trades a few days of latency for far fewer false alarms.
    # Rolling values are autocorrelated, which understates spread, so they get a
    # stricter threshold.
    rolling_days: int = 1

    @property
    def z_threshold(self) -> float:
        return Z_THRESHOLD if self.rolling_days == 1 else Z_THRESHOLD + 1.0


MONITORS: tuple[Monitor, ...] = (
    # Conversion is watched both daily (sharp breaks) and on a trailing week (slow
    # erosion a few percent at a time, which never clears a single-day threshold).
    Monitor("conversion"),
    Monitor("conversion", rolling_days=7),
    Monitor("conversion", "platform"),
    Monitor("conversion", "platform", rolling_days=7),
    Monitor("conversion", "traffic_source", rolling_days=7),
    Monitor("payment_success_rate"),
    Monitor("payment_success_rate", "platform"),
    Monitor("payment_success_rate", "payment_method"),
    Monitor("payment_success_rate", "app_version"),
    Monitor("return_rate", rolling_days=7),
    Monitor("return_rate", "category", rolling_days=7),
    Monitor("return_rate", "subcategory", limit=12, rolling_days=7),
    Monitor("search_to_product_view_rate"),
    Monitor("search_to_product_view_rate", "category"),
    Monitor("sessions"),
    Monitor("sessions", "traffic_source"),
    Monitor("bounce_rate", "traffic_source"),
    Monitor("avg_delivery_days"),
    Monitor("avg_delivery_days", "city_tier"),
    Monitor("add_to_cart_rate"),
    Monitor("aov"),
)


class DetectedAnomaly(BaseModel):
    metric_key: str
    filters: list[dict[str, Any]]
    period_start: date
    period_end: date
    expected: float
    actual: float
    baseline_std: float
    zscore: float
    direction: str
    severity: str
    ongoing: bool
    # Daily detail the UI can show without re-querying.
    days: list[dict[str, Any]]


@dataclass
class _Day:
    day: date
    value: float | None
    numerator: float
    denominator: float | None
    expected: float | None = None
    z: float | None = None
    flagged: bool = False
    extras: dict[str, Any] = field(default_factory=dict)


def _series_days(points: list[Point], start: date, end: date) -> list[_Day]:
    by_day = {str(p.bucket)[:10]: p for p in points}
    days: list[_Day] = []
    d = start
    while d <= end:
        p = by_day.get(d.isoformat())
        if p is None:
            days.append(_Day(day=d, value=None, numerator=0, denominator=None))
        else:
            days.append(_Day(day=d, value=p.value, numerator=p.numerator, denominator=p.denominator))
        d += timedelta(days=1)
    return days


def _rolling(days: list[_Day], window: int, is_ratio: bool) -> list[_Day]:
    """Replace each day with the aggregate of its trailing `window` days."""
    out: list[_Day] = []
    for i, d in enumerate(days):
        if i + 1 < window:
            out.append(_Day(day=d.day, value=None, numerator=0, denominator=None))
            continue
        chunk = [x for x in days[i + 1 - window : i + 1] if x.value is not None]
        if len(chunk) < window:
            out.append(_Day(day=d.day, value=None, numerator=0, denominator=None))
            continue
        num = sum(x.numerator for x in chunk)
        den = sum(x.denominator or 0 for x in chunk)
        mean = sum(x.value or 0 for x in chunk) / len(chunk)
        value = (num / den if den else None) if is_ratio else mean
        out.append(_Day(day=d.day, value=value, numerator=num, denominator=den if is_ratio else None))
    return out


def _mad(values: list[float], center: float) -> float:
    return median(abs(v - center) for v in values)


def _score_days(
    days: list[_Day], *, is_volume: bool, min_denominator: float, z_threshold: float = Z_THRESHOLD
) -> None:
    """Fill expected / z / flagged for each day, walking forward in time.

    Days already flagged are excluded from later baselines. That is what lets a
    regression that started three weeks ago still read as anomalous today: the
    baseline stays anchored to how the metric behaved before the shift instead
    of quietly absorbing it.
    """
    for i, target in enumerate(days):
        if target.value is None:
            continue
        if target.denominator is not None and target.denominator < min_denominator:
            continue
        candidates = [
            d
            for d in days[max(0, i - BASELINE_LOOKBACK_DAYS) : i]
            if d.value is not None
            and not d.flagged
            and (d.denominator is None or d.denominator >= min_denominator)
        ]
        baseline = candidates[-BASELINE_DAYS:]
        if len(baseline) < MIN_BASELINE_POINTS:
            continue
        values = [d.value for d in baseline if d.value is not None]
        center = median(values)
        spread = 1.4826 * _mad(values, center)
        if spread <= 0:
            # Flat baseline: fall back to a small fraction of the level so a real
            # move still registers without dividing by zero.
            spread = max(abs(center) * 0.02, 1e-9)

        expected = center
        if is_volume:
            same_weekday = [d.value for d in baseline if d.day.weekday() == target.day.weekday()]
            if len(same_weekday) >= 2 and center > 0:
                expected = center * (median(same_weekday) / center)
        if target.denominator and 0 < expected < 1:
            # A proportion cannot be steadier than its own sampling noise; MAD over 28
            # points regularly underestimates it and would flag ordinary binomial wobble.
            spread = max(spread, sqrt(expected * (1 - expected) / target.denominator))
        z = (target.value - expected) / spread
        rel = (target.value - expected) / expected if expected else 0.0
        target.expected = expected
        target.z = z
        target.extras = {"relative_change": rel}
        prev = next((d for d in reversed(days[max(0, i - 2) : i]) if d.value is not None), None)
        continuing = (
            prev is not None
            and prev.flagged
            and prev.z is not None
            and (prev.z > 0) == (z > 0)
            and abs(z) >= CONTINUATION_Z
        )
        target.flagged = abs(rel) >= MIN_RELATIVE_CHANGE and (abs(z) >= z_threshold or continuing)


def _significant(windows: list[list[_Day]]) -> list[list[_Day]]:
    """Drop one-day windows unless the day is extreme."""
    return [
        w for w in windows if len(w) > 1 or abs(max(w, key=lambda d: abs(d.z or 0)).z or 0) >= SINGLE_DAY_Z
    ]


def _severity(z: float, rel: float, days: int) -> str:
    """Severity blends magnitude with persistence: one bad day is noise until it repeats."""
    if days == 1:
        return "medium" if abs(z) >= 6 else "low"
    if abs(z) >= 6 or abs(rel) >= 0.30 or (days >= 5 and abs(rel) >= 0.10):
        return "high"
    if abs(z) >= 4 or abs(rel) >= 0.15 or days >= 3:
        return "medium"
    return "low"


def _windows(days: list[_Day]) -> list[list[_Day]]:
    """Group flagged days into windows, tolerating a single unflagged day between them."""
    windows: list[list[_Day]] = []
    current: list[_Day] = []
    gap = 0
    for i, d in enumerate(days):
        if d.flagged:
            if current and gap == 1:
                current.append(days[i - 1])  # bridge the single unflagged day
            current.append(d)
            gap = 0
        elif current:
            gap += 1
            if gap > 1:
                windows.append(current)
                current, gap = [], 0
    if current:
        windows.append(current)
    return windows


def _aggregate(window: list[_Day], is_ratio: bool) -> tuple[float, float]:
    """Actual and expected over the window: ratio metrics re-aggregate from num/den."""
    if is_ratio and all(d.denominator for d in window):
        num = sum(d.numerator for d in window)
        den = sum(d.denominator or 0 for d in window)
        actual = num / den if den else 0.0
    else:
        actual = sum(d.value or 0 for d in window) / len(window)
    expected = sum(d.expected or 0 for d in window) / len(window)
    return actual, expected


def detect_for_monitor(monitor: Monitor, as_of: date) -> list[DetectedAnomaly]:
    m = get_metric(monitor.metric)
    start = as_of - timedelta(days=BASELINE_LOOKBACK_DAYS + DETECTION_WINDOW_DAYS - 1)
    horizon = as_of - timedelta(days=DETECTION_WINDOW_DAYS - 1)
    result = run_metric_query(
        MetricQuery(
            metric=monitor.metric,
            date_from=start,
            date_to=as_of,
            filters=list(monitor.filters),
            breakdown=monitor.breakdown,
            granularity="day",
            limit=monitor.limit,
        )
    )
    is_volume = m.denominator is None and m.format.value == "count"
    is_ratio = m.denominator is not None
    min_den = MIN_DAILY_DENOMINATOR if is_ratio else 0
    found: list[DetectedAnomaly] = []

    for series in result.series:
        days = _series_days(series.points, start, as_of)
        if monitor.rolling_days > 1:
            days = _rolling(days, monitor.rolling_days, is_ratio)
            min_den = MIN_ROLLING_DENOMINATOR if is_ratio else 0
        _score_days(days, is_volume=is_volume, min_denominator=min_den, z_threshold=monitor.z_threshold)
        for window in _significant(_windows(days)):
            if window[-1].day < horizon:
                continue  # history, not something to act on now
            # Rolling values already aggregate; re-summing them would double count.
            actual, expected = _aggregate(window, is_ratio and monitor.rolling_days == 1)
            if not expected:
                continue
            peak = max(window, key=lambda d: abs(d.z or 0))
            z = peak.z or 0.0
            rel = (actual - expected) / expected
            filters = [f.model_dump(exclude_none=True) for f in monitor.filters]
            if monitor.breakdown:
                dim = DIMENSIONS[monitor.breakdown]
                value: Any = int(series.key) if dim.ch_type == "UInt32" else series.key
                filters.append({"dimension": monitor.breakdown, "operator": "eq", "value": value})
            spread = abs((peak.value or 0) - (peak.expected or 0)) / abs(z) if z else 0.0
            detail_from = window[0].day - timedelta(days=21)
            found.append(
                DetectedAnomaly(
                    metric_key=m.key,
                    filters=filters,
                    period_start=window[0].day,
                    period_end=window[-1].day,
                    expected=expected,
                    actual=actual,
                    baseline_std=spread,
                    zscore=z,
                    direction="up" if actual > expected else "down",
                    severity=_severity(z, rel, len(window)),
                    ongoing=window[-1].day >= as_of,
                    days=[
                        {
                            "day": d.day.isoformat(),
                            "value": d.value,
                            "expected": d.expected,
                            "z": d.z,
                            "denominator": d.denominator,
                            "flagged": d.flagged,
                        }
                        for d in days
                        if d.day >= detail_from
                    ],
                )
            )
    return found


def detect_all(as_of: date, monitors: tuple[Monitor, ...] = MONITORS) -> list[DetectedAnomaly]:
    found: list[DetectedAnomaly] = []
    for monitor in monitors:
        try:
            found.extend(detect_for_monitor(monitor, as_of))
        except Exception as exc:  # one broken monitor should not stop the sweep
            log.warning(
                "anomaly_monitor_failed",
                metric=monitor.metric,
                breakdown=monitor.breakdown,
                error=str(exc),
            )
    return found


def _filter_key(f: dict[str, Any]) -> tuple[str, str, str, str]:
    return (f["dimension"], f.get("operator", "eq"), str(f.get("value")), str(f.get("values")))


def same_filters(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> bool:
    return sorted(map(_filter_key, a)) == sorted(map(_filter_key, b))


def persist(db: Session, project_id: int, detected: list[DetectedAnomaly], now: datetime) -> dict[str, int]:
    """Upsert detected windows: an anomaly that grew by a day updates in place."""
    earliest = min((d.period_start for d in detected), default=now.date())
    existing = list(
        db.scalars(
            select(Anomaly).where(
                Anomaly.project_id == project_id,
                Anomaly.period_end >= earliest - timedelta(days=2),
            )
        )
    )
    created = updated = 0
    for d in detected:
        match = next(
            (
                a
                for a in existing
                if a.metric_key == d.metric_key
                and same_filters(a.filters, d.filters)
                and a.period_end >= d.period_start - timedelta(days=1)
                and a.period_start <= d.period_end + timedelta(days=1)
            ),
            None,
        )
        if match is None:
            db.add(
                Anomaly(
                    project_id=project_id,
                    metric_key=d.metric_key,
                    filters=d.filters,
                    period_start=d.period_start,
                    period_end=d.period_end,
                    expected=d.expected,
                    actual=d.actual,
                    baseline_std=d.baseline_std,
                    zscore=d.zscore,
                    direction=d.direction,
                    severity=d.severity,
                    detected_at=now,
                )
            )
            created += 1
        else:
            match.period_start = min(match.period_start, d.period_start)
            match.period_end = max(match.period_end, d.period_end)
            match.expected = d.expected
            match.actual = d.actual
            match.baseline_std = d.baseline_std
            match.zscore = d.zscore
            match.direction = d.direction
            match.severity = d.severity
            updated += 1
    db.flush()
    return {"detected": len(detected), "created": created, "updated": updated}


def run_detection(db: Session, project_id: int, as_of: date, now: datetime) -> dict[str, int]:
    detected = detect_all(as_of)
    # Prefer the most specific window per metric: the global series and one of
    # its breakdowns often fire together, which is useful (it tells you where the
    # move is concentrated), so both are kept.
    summary = persist(db, project_id, detected, now)
    log.info("anomaly_detection_complete", as_of=str(as_of), **summary)
    return summary
