"""Anomaly detector on synthetic daily series. No database involved."""

from __future__ import annotations

import random
from datetime import date, timedelta

import pytest

from probelens.analytics.anomalies import (
    BASELINE_DAYS,
    MIN_DAILY_DENOMINATOR,
    _Day,
    _rolling,
    _score_days,
    _severity,
    _significant,
    _windows,
)

START = date(2026, 6, 1)


def _ratio_series(
    rate: float,
    days: int,
    den: int = 2000,
    seed: int = 1,
    shift_from: int | None = None,
    shift_to: float = 0.0,
) -> list[_Day]:
    rng = random.Random(seed)
    out: list[_Day] = []
    for i in range(days):
        p = shift_to if shift_from is not None and i >= shift_from else rate
        num = sum(1 for _ in range(den) if rng.random() < p)
        out.append(_Day(day=START + timedelta(days=i), value=num / den, numerator=num, denominator=den))
    return out


@pytest.mark.parametrize("seed", range(6))
def test_flat_series_is_quiet(seed: int) -> None:
    days = _ratio_series(0.05, 70, seed=seed)
    _score_days(days, is_volume=False, min_denominator=MIN_DAILY_DENOMINATOR)
    assert _significant(_windows(days)) == []


def test_step_change_is_flagged_and_baseline_stays_anchored() -> None:
    days = _ratio_series(0.05, 80, shift_from=50, shift_to=0.03)
    _score_days(days, is_volume=False, min_denominator=MIN_DAILY_DENOMINATOR)
    flagged = [d for d in days if d.flagged]
    assert flagged, "a 40% drop on 2,000/day must be detected"
    assert flagged[0].day <= START + timedelta(days=51)
    # 30 days into the regression the expected value still reflects the pre-shift level:
    # flagged days are excluded from the baseline, so it cannot drift down to 3%.
    last = days[-1]
    assert last.expected is not None and last.expected > 0.045
    assert last.flagged


def test_noisy_low_volume_ratio_needs_rolling_window() -> None:
    # 6% conversion on 800 sessions/day; a 30% drop is inside daily noise but obvious weekly.
    daily = _ratio_series(0.06, 80, den=800, seed=7, shift_from=50, shift_to=0.042)
    _score_days(daily, is_volume=False, min_denominator=MIN_DAILY_DENOMINATOR)
    rolled = _rolling(_ratio_series(0.06, 80, den=800, seed=7, shift_from=50, shift_to=0.042), 7, True)
    _score_days(rolled, is_volume=False, min_denominator=200, z_threshold=4.0)
    assert sum(d.flagged for d in rolled) > sum(d.flagged for d in daily)
    assert rolled[-1].flagged


def test_windows_bridge_single_gap_days() -> None:
    days = _ratio_series(0.05, 12)
    for i in (3, 4, 6, 7, 10):
        days[i].flagged = True
    windows = _windows(days)
    assert [len(w) for w in windows] == [5, 1]  # 3,4,(5),6,7 bridged; 10 alone


def test_small_denominators_are_skipped() -> None:
    days = _ratio_series(0.05, 40, den=30)
    _score_days(days, is_volume=False, min_denominator=MIN_DAILY_DENOMINATOR)
    assert all(d.z is None for d in days)


def test_severity_requires_persistence() -> None:
    assert _severity(z=4.5, rel=-0.2, days=1) == "low"
    assert _severity(z=7.0, rel=-0.2, days=1) == "medium"
    assert _severity(z=4.5, rel=-0.2, days=3) == "medium"
    assert _severity(z=4.5, rel=-0.12, days=6) == "high"
    assert _severity(z=3.2, rel=-0.35, days=2) == "high"


def test_baseline_uses_at_most_baseline_days_points() -> None:
    days = _ratio_series(0.05, BASELINE_DAYS + 30)
    _score_days(days, is_volume=False, min_denominator=MIN_DAILY_DENOMINATOR)
    assert days[-1].expected is not None
