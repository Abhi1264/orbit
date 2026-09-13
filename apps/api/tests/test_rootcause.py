"""Rate/mix decomposition and candidate heuristics on hand-built series."""

from __future__ import annotations

import pytest

from probelens.analytics.metrics import get_metric
from probelens.analytics.query import Series, Total
from probelens.analytics.rootcause import (
    Change,
    DimensionBreakdown,
    _concentration,
    _decompose,
    _uniform_dimensions,
)


def _series(key: str, base_num: float, base_den: float, per_num: float, per_den: float) -> Series:
    return Series(
        key=key,
        label=key,
        total=Total(value=per_num / per_den, numerator=per_num, denominator=per_den),
        compare_total=Total(value=base_num / base_den, numerator=base_num, denominator=base_den),
    )


def _change(series: list[Series]) -> Change:
    bn = sum(s.compare_total.numerator for s in series if s.compare_total)
    bd = sum(s.compare_total.denominator or 0 for s in series if s.compare_total)
    pn = sum(s.total.numerator for s in series)
    pd = sum(s.total.denominator or 0 for s in series)
    b, p = bn / bd, pn / pd
    return Change(
        baseline=b,
        period=p,
        abs_change=p - b,
        rel_change=(p - b) / b,
        baseline_numerator=bn,
        baseline_denominator=bd,
        period_numerator=pn,
        period_denominator=pd,
    )


CONVERSION = get_metric("conversion")


def test_decomposition_sums_to_the_whole_change() -> None:
    # android's rate halves, ios and web are flat; shares unchanged.
    series = [
        _series("android", 300, 6000, 150, 6000),
        _series("ios", 120, 2000, 120, 2000),
        _series("web", 100, 2000, 100, 2000),
    ]
    contribs = _decompose(CONVERSION, _change(series), series, 7, 7)
    assert pytest.approx(sum(c.explained or 0 for c in contribs), abs=1e-9) == 1.0
    android = next(c for c in contribs if c.key == "android")
    assert android.explained == pytest.approx(1.0)
    assert android.mix_effect == pytest.approx(0.0)
    assert contribs[0].key == "android"  # sorted by |explained|


def test_pure_mix_shift_has_no_rate_effect() -> None:
    # Every segment keeps its own rate, but volume moves from a 10% segment to a 2% one.
    series = [
        _series("good", 500, 5000, 200, 2000),
        _series("bad", 100, 5000, 160, 8000),
    ]
    contribs = _decompose(CONVERSION, _change(series), series, 7, 7)
    for c in contribs:
        assert c.rate_effect == pytest.approx(0.0, abs=1e-9)
    assert pytest.approx(sum(c.mix_effect or 0 for c in contribs) / (_change(series).abs_change or 1)) == 1.0


def test_new_segment_is_measured_against_baseline_average() -> None:
    series = [
        _series("8.3.1", 500, 10000, 100, 2000),
        Series(
            key="8.4.0",
            label="8.4.0",
            total=Total(value=0.02, numerator=160, denominator=8000),
            compare_total=None,
        ),
    ]
    contribs = _decompose(CONVERSION, _change(series), series, 7, 7)
    new = next(c for c in contribs if c.key == "8.4.0")
    assert new.is_new
    assert new.share_baseline == 0
    assert new.explained is not None and new.explained > 0.9


def test_concentration_discounts_dominant_segments() -> None:
    series = [_series("a", 950, 9500, 475, 9500), _series("b", 50, 500, 25, 500)]
    contribs = _decompose(CONVERSION, _change(series), series, 7, 7)
    # Both halve; "a" explains 95% but is 95% of volume, so the dimension is not informative.
    assert _concentration(contribs) < 0.1


def test_uniform_dimensions_detects_scope_wide_moves() -> None:
    def breakdown(dim: str, rates: list[tuple[str, float, float, float]]) -> DimensionBreakdown:
        series = [_series(k, b * 1000 * s, 1000 * s, p * 1000 * s, 1000 * s) for k, s, b, p in rates]
        contribs = _decompose(CONVERSION, _change(series), series, 7, 7)
        return DimensionBreakdown(
            dimension=dim, label=dim, contributions=contribs, concentration=0, additive=True
        )

    uniform = breakdown(
        "platform", [("android", 6, 0.06, 0.03), ("ios", 3, 0.06, 0.032), ("web", 1, 0.06, 0.028)]
    )
    skewed = breakdown("city_tier", [("t1", 6, 0.06, 0.06), ("t2", 3, 0.06, 0.02), ("t3", 1, 0.06, 0.06)])
    overall_rel = -0.5
    uni, judgeable = _uniform_dimensions([uniform, skewed], overall_rel)
    assert judgeable == ["platform", "city_tier"]
    assert uni == ["platform"]
    # A negligible overall move is never "uniform": there is nothing to explain.
    assert _uniform_dimensions([uniform], 0.01) == ([], [])
