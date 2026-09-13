"""Rule-based ship / iterate / stop / continue recommendation.

The rules are deliberately boring and fully explained: every recommendation
lists the checks it ran and the ones that failed. It is input to a human's
decision memo, not a replacement for it.
"""

from __future__ import annotations

from datetime import date

from probelens.analytics.metrics import format_value, get_metric
from probelens.experiments.analysis import (
    Check,
    ExperimentSpec,
    Exposure,
    MetricReadout,
    Power,
    Recommendation,
    VariantComparison,
)

# A guardrail whose interval still allows this much relative degradation has not
# ruled out a material regression, whatever its p-value says.
GUARDRAIL_TOLERANCE = 0.10


def _pick_treatment(primary: MetricReadout) -> VariantComparison | None:
    """The variant to judge: the significant one with the best lift, else the best point estimate."""
    if not primary.comparisons:
        return None
    sign = 1 if primary.higher_is_better else -1
    sig = [c for c in primary.comparisons if c.significant]
    pool = sig or primary.comparisons
    return max(pool, key=lambda c: sign * c.abs_diff)


def _fmt(metric_key: str, value: float | None) -> str:
    return format_value(get_metric(metric_key).format, value)


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:+.1f}%"


def recommend(
    spec: ExperimentSpec, exposure: Exposure, metrics: list[MetricReadout], power: Power, as_of: date
) -> Recommendation:
    primary = metrics[0]
    guardrails = metrics[1:]
    checks: list[Check] = []
    reasons: list[str] = []
    risks: list[str] = []
    ended = spec.end is not None and as_of > spec.end

    # 1. Trust: is the split what we configured?
    if exposure.srm is None:
        checks.append(
            Check(name="Sample ratio", passed=False, detail="Fewer than two variants have exposures.")
        )
    else:
        split = " / ".join(f"{k} {v:,}" for k, v in sorted(exposure.by_variant.items()))
        checks.append(
            Check(
                name="Sample ratio",
                passed=not exposure.srm.mismatch,
                detail=f"{split} (χ² p = {exposure.srm.p_value:.3g}). "
                + (
                    "Matches the configured split."
                    if not exposure.srm.mismatch
                    else "Does not match the configured split."
                ),
            )
        )
    if exposure.srm is None or exposure.srm.mismatch:
        return Recommendation(
            decision="stop",
            confidence="high",
            headline="Do not read these results: the sample ratio does not match the configured split",
            reasons=[
                "A sample ratio mismatch means assignment or "
                "exposure logging is broken, which biases every metric.",
                "Fix the assignment/logging path, then restart the experiment.",
            ],
            risks=[],
            checks=checks,
        )

    # 2. Sample size and duration.
    sample_ok = power.smallest_variant_n >= spec.min_sample_per_variant
    checks.append(
        Check(
            name="Minimum sample",
            passed=sample_ok,
            detail=f"Smallest variant has {power.smallest_variant_n:,} "
            f"users; minimum is {spec.min_sample_per_variant:,}.",
        )
    )
    duration_ok = exposure.days_running >= spec.min_duration_days
    checks.append(
        Check(
            name="Minimum duration",
            passed=duration_ok,
            detail=f"Ran {exposure.days_running} days; minimum is "
            f"{spec.min_duration_days} to cover weekly seasonality.",
        )
    )
    powered = (
        power.detectable_effect_now is not None and power.detectable_effect_now <= spec.min_relative_effect
    )
    checks.append(
        Check(
            name="Statistical power",
            passed=powered,
            detail=(
                f"Can currently detect a {_pct(power.detectable_effect_now)} relative change with 80% power; "
                f"the target was ±{spec.min_relative_effect * 100:.0f}%."
                + (
                    f" About {power.required_n_per_variant:,} users per variant are needed."
                    if power.required_n_per_variant
                    else ""
                )
            ),
        )
    )

    # 3. Primary metric.
    t = _pick_treatment(primary)
    if t is None:
        checks.append(Check(name="Primary metric", passed=False, detail="No treatment variant to compare."))
        return Recommendation(
            decision="continue",
            confidence="low",
            headline="Not enough data to compare variants yet",
            reasons=["The primary metric has no treatment/control comparison."],
            risks=[],
            checks=checks,
        )
    control_stat = next((v for v in primary.variants if v.key == spec.control_key), None)
    treat_stat = next((v for v in primary.variants if v.key == t.variant), None)
    primary_detail = (
        f"{primary.label}: {t.variant} "
        f"{_fmt(primary.metric_key, treat_stat.value if treat_stat else None)} vs "
        f"{spec.control_key} {_fmt(primary.metric_key, control_stat.value if control_stat else None)} "
        f"({_pct(t.rel_diff)}, 95% CI {_pct(t.rel_ci_low)} to {_pct(t.rel_ci_high)}, p = {t.p_value:.3g})."
    )
    checks.append(Check(name="Primary metric", passed=t.direction == "better", detail=primary_detail))

    # 4. Guardrails.
    hurt: list[tuple[MetricReadout, VariantComparison]] = []
    inconclusive: list[tuple[MetricReadout, VariantComparison, float]] = []
    for g in guardrails:
        c = next((x for x in g.comparisons if x.variant == t.variant), None)
        if c is None:
            checks.append(
                Check(name=f"Guardrail · {g.label}", passed=True, detail="No comparison available.")
            )
            continue
        worse = c.direction == "worse"
        if worse:
            hurt.append((g, c))
        else:
            # "Not significant" is not "safe": if the point estimate leans the wrong way and the
            # interval still allows a material regression, the guardrail has not done its job.
            bad_point = (c.rel_diff or 0) < 0 if g.higher_is_better else (c.rel_diff or 0) > 0
            bad_bound = -(c.rel_ci_low or 0) if g.higher_is_better else (c.rel_ci_high or 0)
            if bad_point and bad_bound > GUARDRAIL_TOLERANCE:
                inconclusive.append((g, c, bad_bound))
        checks.append(
            Check(
                name=f"Guardrail · {g.label}",
                passed=not worse,
                detail=f"{_pct(c.rel_diff)} (95% CI {_pct(c.rel_ci_low)} "
                f"to {_pct(c.rel_ci_high)}, p = {c.p_value:.3g}). "
                + ("Significantly worse." if worse else "Not significantly worse."),
            )
        )
    for g, c, bound in inconclusive:
        risks.append(
            f"{g.label} is inconclusive rather than safe: the "
            f"point estimate is {_pct(c.rel_diff)} and the interval "
            f"allows up to {bound * 100:.0f}% worse. The experiment is underpowered on this guardrail."
        )

    # 5. Decide.
    if t.direction == "better" and not hurt:
        if sample_ok and duration_ok:
            conf: str = "high" if powered else "medium"
            reasons.append(primary_detail)
            reasons.append("No guardrail metric is significantly worse.")
            if not powered:
                risks.append(
                    "The experiment is not powered for the target "
                    "effect; the lift is significant but its size "
                    "is uncertain, so expect some regression to the mean after shipping."
                )
            headline = f"Ship {t.variant}: {primary.label} improved {_pct(t.rel_diff)} with guardrails intact"
            if inconclusive:
                conf = "medium" if conf == "high" else "low"
                names = ", ".join(g.label.lower() for g, _, _ in inconclusive)
                headline = (
                    f"Ship {t.variant} with a follow-up: "
                    f"{primary.label} improved {_pct(t.rel_diff)}, {names} unresolved"
                )
                reasons.append(
                    f"Guardrail check on {names} is not conclusive; "
                    "ship with a post-launch monitor and a kill criterion."
                )
            return Recommendation(
                decision="ship",
                confidence=conf,  # type: ignore[arg-type]
                headline=headline,
                reasons=reasons,
                risks=risks,
                checks=checks,
            )
        reasons.append(primary_detail)
        reasons.append(
            "Sample or duration minimums are not met yet; an early significant result often shrinks."
        )
        return Recommendation(
            decision="continue",
            confidence="low",
            headline=f"Promising but early: keep {t.variant} running until minimums are met",
            reasons=reasons,
            risks=["Peeking at early significance inflates the false-positive rate."],
            checks=checks,
        )

    if t.direction == "better" and hurt:
        names = ", ".join(f"{g.label} ({_pct(c.rel_diff)})" for g, c in hurt)
        reasons.append(primary_detail)
        reasons.append(f"Guardrail regression: {names}.")
        reasons.append(
            "A win on the primary metric that damages a guardrail is a trade-off, not a ship decision."
        )
        return Recommendation(
            decision="iterate",
            confidence="high" if powered else "medium",
            headline=f"Iterate: {t.variant} lifts {primary.label} "
            f"but hurts {', '.join(g.label for g, _ in hurt)}",
            reasons=reasons,
            risks=[
                f"Shipping as-is trades {primary.label} against "
                f"{names}; quantify the net business impact first."
            ],
            checks=checks,
        )

    if t.direction == "worse":
        reasons.append(primary_detail)
        reasons.append(f"{t.variant} is significantly worse on the primary metric.")
        return Recommendation(
            decision="stop",
            confidence="high" if (sample_ok and duration_ok) else "medium",
            headline=f"Stop: {t.variant} reduces {primary.label} by {_pct(t.rel_diff)}",
            reasons=reasons,
            risks=[],
            checks=checks,
        )

    # Flat.
    reasons.append(primary_detail)
    if hurt:
        names = ", ".join(f"{g.label} ({_pct(c.rel_diff)})" for g, c in hurt)
        reasons.append(f"No detectable primary lift, and guardrails regressed: {names}.")
        return Recommendation(
            decision="stop",
            confidence="high" if powered else "medium",
            headline=f"Stop: no lift on {primary.label} and {', '.join(g.label for g, _ in hurt)} got worse",
            reasons=reasons,
            risks=[],
            checks=checks,
        )
    if powered and duration_ok:
        reasons.append(
            f"The experiment could detect a ±{spec.min_relative_effect * 100:.0f}% change and did not; "
            "any real effect is smaller than the lift that would justify shipping."
        )
        return Recommendation(
            decision="stop",
            confidence="high",
            headline=f"Stop: no detectable effect on {primary.label} at the target lift",
            reasons=reasons,
            risks=[
                "A smaller-than-target effect may still exist; "
                "decide whether it would be worth the complexity."
            ],
            checks=checks,
        )
    if ended:
        reasons.append("The experiment ended before reaching the sample needed to detect the target effect.")
        return Recommendation(
            decision="iterate",
            confidence="low",
            headline="Inconclusive: underpowered when it ended",
            reasons=reasons,
            risks=["Re-running with more traffic or a larger expected effect is the only way to learn more."],
            checks=checks,
        )
    eta = (
        f" (~{power.projected_days_to_power} more days at the current rate)"
        if power.projected_days_to_power
        else ""
    )
    reasons.append(f"Not yet powered for a ±{spec.min_relative_effect * 100:.0f}% change{eta}.")
    return Recommendation(
        decision="continue",
        confidence="low",
        headline=f"Keep running: no significant change yet and the experiment is not powered{eta}",
        reasons=reasons,
        risks=["Do not stop on an early read; wait for the sample size or the planned end date."],
        checks=checks,
    )
