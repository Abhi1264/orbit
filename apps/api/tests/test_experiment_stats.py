"""Experiment statistics: delta-method variance, z-tests, SRM, power."""

import random
from math import sqrt

import pytest

from probelens.experiments import stats
from probelens.experiments.assignment import VariantSpec, assign, variant_for_bucket
from probelens.experiments.stats import VariantMoments


def _moments(nums: list[float], dens: list[float]) -> VariantMoments:
    n = len(nums)
    mean_n, mean_d = sum(nums) / n, sum(dens) / n
    var_n = sum((x - mean_n) ** 2 for x in nums) / (n - 1)
    var_d = sum((x - mean_d) ** 2 for x in dens) / (n - 1)
    cov = sum((x - mean_n) * (y - mean_d) for x, y in zip(nums, dens, strict=True)) / (n - 1)
    return VariantMoments(n=n, sum_num=sum(nums), sum_den=sum(dens), var_num=var_n, var_den=var_d, cov=cov)


def _bernoulli(rng: random.Random, n: int, p: float) -> VariantMoments:
    xs = [1.0 if rng.random() < p else 0.0 for _ in range(n)]
    return _moments(xs, [1.0] * n)


def test_delta_method_reduces_to_binomial_for_one_trial_per_user() -> None:
    rng = random.Random(1)
    m = _bernoulli(rng, 5000, 0.2)
    p = m.value
    assert p is not None
    # With den = 1 for everyone, the ratio-of-sums variance is the plain proportion variance.
    assert m.variance == pytest.approx(p * (1 - p) / m.n, rel=0.01)


def test_users_with_many_sessions_widen_the_interval() -> None:
    """Session-level rate with per-user clustering: the naive binomial on sessions is too tight."""
    rng = random.Random(2)
    nums: list[float] = []
    dens: list[float] = []
    for _ in range(3000):
        sessions = rng.choice([1, 1, 2, 3, 6])
        p_user = rng.betavariate(2, 8)  # users differ in their own conversion propensity
        conv = sum(1 for _ in range(sessions) if rng.random() < p_user)
        nums.append(conv)
        dens.append(sessions)
    m = _moments(nums, dens)
    assert m.value is not None and m.variance is not None
    naive = m.value * (1 - m.value) / m.sum_den
    assert m.variance > naive * 1.2


def test_compare_detects_a_real_lift_and_not_a_null() -> None:
    rng = random.Random(3)
    control = _bernoulli(rng, 20000, 0.20)
    treatment = _bernoulli(rng, 20000, 0.22)
    c = stats.compare(control, treatment)
    assert c is not None
    assert c.significant and c.abs_diff > 0 and c.ci_low > 0
    assert c.rel_diff == pytest.approx(0.10, abs=0.05)

    null = stats.compare(control, _bernoulli(rng, 20000, 0.20))
    assert null is not None
    assert not null.significant
    assert null.ci_low < 0 < null.ci_high


def test_false_positive_rate_is_near_alpha() -> None:
    rng = random.Random(4)
    hits = 0
    trials = 400
    for _ in range(trials):
        a = _bernoulli(rng, 800, 0.3)
        b = _bernoulli(rng, 800, 0.3)
        c = stats.compare(a, b)
        assert c is not None
        hits += c.significant
    assert 0.02 <= hits / trials <= 0.09


def test_chi2_sf_matches_known_values() -> None:
    assert stats.chi2_sf(3.841, 1) == pytest.approx(0.05, abs=0.001)
    assert stats.chi2_sf(5.991, 2) == pytest.approx(0.05, abs=0.001)
    assert stats.chi2_sf(0.0, 1) == 1.0
    assert stats.chi2_sf(50.0, 1) < 1e-10


def test_sample_ratio_mismatch() -> None:
    ok = stats.sample_ratio_mismatch({"control": 10050, "treatment": 9950}, {"control": 50, "treatment": 50})
    assert not ok.mismatch and ok.p_value > 0.3
    bad = stats.sample_ratio_mismatch({"control": 10600, "treatment": 9400}, {"control": 50, "treatment": 50})
    assert bad.mismatch and bad.p_value < 1e-6
    uneven = stats.sample_ratio_mismatch({"a": 9000, "b": 1000}, {"a": 90, "b": 10})
    assert not uneven.mismatch


def test_required_sample_size_matches_textbook() -> None:
    # 20% baseline, +5% relative (1pp absolute), alpha .05 power .8: about 25k per arm.
    n = stats.required_n_per_variant(0.20, 0.20 * 0.80, 0.05)
    assert n is not None
    assert 24000 <= n <= 26500
    mde = stats.detectable_effect(0.20, 0.16, n)
    assert mde == pytest.approx(0.05, rel=0.02)


def test_normal_quantile_roundtrip() -> None:
    assert stats.z_for_alpha(0.05) == pytest.approx(1.95996, abs=1e-4)
    assert stats.two_sided_p(1.95996) == pytest.approx(0.05, abs=1e-4)
    assert stats.two_sided_p(0.0) == 1.0


# --------------------------------------------------------------------------- assignment


def test_assignment_split_matches_weights() -> None:
    variants = [VariantSpec("control", 50), VariantSpec("treatment", 50)]
    counts = {"control": 0, "treatment": 0, None: 0}
    for uid in range(1, 20001):
        counts[assign("exp", uid, variants, traffic_percent=50)] += 1
    assert counts[None] == pytest.approx(10000, abs=350)
    assert counts["control"] == pytest.approx(5000, abs=250)
    assert counts["treatment"] == pytest.approx(5000, abs=250)


def test_assignment_is_stable_and_independent_across_experiments() -> None:
    variants = [VariantSpec("a", 50), VariantSpec("b", 50)]
    first = [assign("x", u, variants) for u in range(1, 2001)]
    assert first == [assign("x", u, variants) for u in range(1, 2001)]
    other = [assign("y", u, variants) for u in range(1, 2001)]
    agree = sum(1 for p, q in zip(first, other, strict=True) if p == q)
    assert 850 <= agree <= 1150  # ~50%: the two hashes are unrelated


def test_variant_for_bucket_edges() -> None:
    variants = [VariantSpec("a", 25), VariantSpec("b", 75)]
    assert variant_for_bucket(0, variants, 10000) == "a"
    assert variant_for_bucket(2499, variants, 10000) == "a"
    assert variant_for_bucket(2500, variants, 10000) == "b"
    assert variant_for_bucket(9999, variants, 10000) == "b"


def test_variance_never_negative() -> None:
    m = VariantMoments(n=10, sum_num=5, sum_den=10, var_num=0.0, var_den=0.0, cov=1.0)
    assert m.variance is not None and m.variance >= 0
    assert sqrt(m.variance) >= 0
