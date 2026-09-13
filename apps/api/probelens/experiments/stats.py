"""Statistics for experiment readouts. Pure functions, no I/O.

Every metric is analysed at the unit of randomisation (the user). A variant is
summarised by per-user sums and their second moments, and a metric value is the
ratio of sums Σnum / Σden. Its variance comes from the delta method, which is
what makes session-level rates (conversion, add-to-cart) honest when users have
many sessions: treating sessions as independent would understate the variance
and overstate significance. Per-user means (revenue per user) are the special
case den = 1, where the delta method reduces to the ordinary t-test variance.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import erfc, exp, isfinite, lgamma, log, pi, sqrt

Z_95 = 1.959963984540054
Z_80_POWER = 0.8416212335729143


@dataclass(frozen=True)
class VariantMoments:
    """Per-variant sufficient statistics over users."""

    n: int
    sum_num: float
    sum_den: float
    var_num: float  # sample variance of per-user numerators
    var_den: float  # sample variance of per-user denominators
    cov: float  # sample covariance of per-user (num, den)

    @property
    def value(self) -> float | None:
        return self.sum_num / self.sum_den if self.sum_den else None

    @property
    def variance(self) -> float | None:
        """Variance of the ratio-of-sums estimator (delta method)."""
        if self.n < 2 or not self.sum_den:
            return None
        r = self.sum_num / self.sum_den
        mean_den = self.sum_den / self.n
        v = (self.var_num - 2 * r * self.cov + r * r * self.var_den) / (mean_den**2)
        return max(v, 0.0) / self.n


@dataclass(frozen=True)
class Comparison:
    control: float
    treatment: float
    abs_diff: float
    rel_diff: float | None
    ci_low: float  # 95% CI on the absolute difference
    ci_high: float
    rel_ci_low: float | None
    rel_ci_high: float | None
    z: float
    p_value: float
    significant: bool

    @property
    def ci_excludes_zero(self) -> bool:
        return self.ci_low > 0 or self.ci_high < 0


def normal_sf(z: float) -> float:
    """P(Z > z) for a standard normal."""
    return 0.5 * erfc(z / sqrt(2))


def two_sided_p(z: float) -> float:
    return min(1.0, 2 * normal_sf(abs(z)))


def compare(control: VariantMoments, treatment: VariantMoments, alpha: float = 0.05) -> Comparison | None:
    """Difference in the ratio-of-sums between two variants with a normal approximation.

    For proportions this is the two-proportion z-test with user-clustered variance;
    for per-user means it is Welch's t-test (normal-approximated, which is exact
    enough at the sample sizes an experiment needs to be readable at all).
    """
    c, t = control.value, treatment.value
    vc, vt = control.variance, treatment.variance
    if c is None or t is None or vc is None or vt is None:
        return None
    se = sqrt(vc + vt)
    diff = t - c
    z = diff / se if se else (0.0 if diff == 0 else float("inf"))
    p = two_sided_p(z) if isfinite(z) else 0.0
    zcrit = z_for_alpha(alpha)
    lo, hi = diff - zcrit * se, diff + zcrit * se
    rel = diff / c if c else None
    return Comparison(
        control=c,
        treatment=t,
        abs_diff=diff,
        rel_diff=rel,
        ci_low=lo,
        ci_high=hi,
        rel_ci_low=(lo / c) if c else None,
        rel_ci_high=(hi / c) if c else None,
        z=z,
        p_value=p,
        significant=p < alpha,
    )


def z_for_alpha(alpha: float) -> float:
    """Two-sided critical value. Only common alphas are needed; others fall back to bisection."""
    table = {0.10: 1.6448536269514722, 0.05: Z_95, 0.01: 2.5758293035489004}
    if alpha in table:
        return table[alpha]
    return _normal_quantile(1 - alpha / 2)


def _normal_quantile(p: float) -> float:
    lo, hi = -10.0, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if 1 - normal_sf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def chi2_sf(x: float, df: int) -> float:
    """Survival function of a chi-square with integer df, via the regularised upper
    incomplete gamma Q(df/2, x/2). Series for small x, continued fraction otherwise."""
    if x <= 0:
        return 1.0
    a, z = df / 2.0, x / 2.0
    if z < a + 1:
        # Lower series, then complement.
        term = 1.0 / a
        total = term
        n = 1
        while abs(term) > 1e-15 * abs(total) and n < 10_000:
            term *= z / (a + n)
            total += term
            n += 1
        p = total * exp(-z + a * log(z) - lgamma(a))
        return max(0.0, min(1.0, 1 - p))
    # Lentz continued fraction for the upper incomplete gamma.
    tiny = 1e-300
    b = z + 1 - a
    c = 1 / tiny
    d = 1 / b
    h = d
    for i in range(1, 10_000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-15:
            break
    q = exp(-z + a * log(z) - lgamma(a)) * h
    return max(0.0, min(1.0, q))


@dataclass(frozen=True)
class SrmResult:
    observed: dict[str, int]
    expected: dict[str, float]
    chi2: float
    p_value: float
    mismatch: bool  # p below the (deliberately strict) alarm threshold


def sample_ratio_mismatch(
    observed: dict[str, int], weights: dict[str, int], alarm_p: float = 0.001
) -> SrmResult:
    """Chi-square goodness of fit of exposure counts against the configured split.

    A sample ratio mismatch means assignment or logging is broken, and every
    downstream number is suspect; the alarm threshold is strict because with tens
    of thousands of users even a benign-looking 50.4/49.6 split is wildly unlikely.
    """
    total = sum(observed.values())
    wsum = sum(weights.get(k, 0) for k in observed) or 1
    expected = {k: total * weights.get(k, 0) / wsum for k in observed}
    chi2 = sum(((observed[k] - e) ** 2 / e) for k, e in expected.items() if e > 0)
    df = max(1, len(observed) - 1)
    p = chi2_sf(chi2, df)
    return SrmResult(observed=observed, expected=expected, chi2=chi2, p_value=p, mismatch=p < alarm_p)


def required_n_per_variant(
    baseline: float,
    per_user_variance: float,
    min_relative_effect: float,
    alpha: float = 0.05,
    power: float = 0.8,
) -> int | None:
    """Users per variant to detect a relative lift of `min_relative_effect` on a metric
    whose per-user ratio has the given variance (variance × n, i.e. the population
    variance of the estimator's unit contribution)."""
    delta = abs(baseline * min_relative_effect)
    if delta <= 0 or per_user_variance <= 0:
        return None
    z_beta = _normal_quantile(power) if power != 0.8 else Z_80_POWER
    n = 2 * ((z_for_alpha(alpha) + z_beta) ** 2) * per_user_variance / (delta**2)
    return int(n) + 1


def detectable_effect(
    baseline: float, per_user_variance: float, n_per_variant: int, alpha: float = 0.05, power: float = 0.8
) -> float | None:
    """Smallest relative lift the current sample could detect with the given power."""
    if baseline <= 0 or per_user_variance <= 0 or n_per_variant <= 0:
        return None
    z_beta = _normal_quantile(power) if power != 0.8 else Z_80_POWER
    delta = (z_for_alpha(alpha) + z_beta) * sqrt(2 * per_user_variance / n_per_variant)
    return delta / baseline


def normal_pdf(x: float) -> float:
    return exp(-0.5 * x * x) / sqrt(2 * pi)
