"""Rule-based recommendation: each branch, driven by synthetic readouts."""

from datetime import date

from probelens.experiments.analysis import (
    ExperimentSpec,
    Exposure,
    MetricReadout,
    Power,
    Srm,
    VariantComparison,
    VariantStat,
)
from probelens.experiments.assignment import VariantSpec
from probelens.experiments.decision import recommend

AS_OF = date(2026, 9, 13)


def _spec(**kw) -> ExperimentSpec:
    base = dict(
        key="exp",
        variants=[VariantSpec("control", 50), VariantSpec("treatment", 50)],
        control_key="control",
        start=date(2026, 8, 20),
        end=date(2026, 9, 10),
        primary_metric="add_to_cart_rate",
        guardrail_metrics=["return_rate"],
        audience_filters=[],
        traffic_percent=100,
        has_exposure_events=True,
        min_sample_per_variant=3000,
        min_relative_effect=0.05,
        min_duration_days=7,
    )
    base.update(kw)
    return ExperimentSpec(**base)


def _exposure(n: int = 15000, mismatch: bool = False) -> Exposure:
    return Exposure(
        total_users=2 * n,
        by_variant={"control": n, "treatment": n},
        first_exposure=date(2026, 8, 20),
        last_exposure=date(2026, 9, 10),
        days_running=22,
        contaminated_users=0,
        srm=Srm(
            chi2=20.0 if mismatch else 0.3, p_value=1e-5 if mismatch else 0.6, mismatch=mismatch, expected={}
        ),
    )


def _readout(
    key: str,
    role: str,
    control: float,
    treatment: float,
    *,
    rel_ci: tuple[float, float],
    p: float,
    higher_is_better: bool = True,
) -> MetricReadout:
    rel = treatment / control - 1
    significant = p < 0.05
    direction = "flat"
    if significant:
        good = treatment > control if higher_is_better else treatment < control
        direction = "better" if good else "worse"
    return MetricReadout(
        metric_key=key,
        label=key.replace("_", " ").capitalize(),
        format="percent",
        higher_is_better=higher_is_better,
        role=role,  # type: ignore[arg-type]
        variants=[
            VariantStat(
                key="control",
                users=15000,
                value=control,
                numerator=0,
                denominator=0,
                ci_low=None,
                ci_high=None,
            ),
            VariantStat(
                key="treatment",
                users=15000,
                value=treatment,
                numerator=0,
                denominator=0,
                ci_low=None,
                ci_high=None,
            ),
        ],
        comparisons=[
            VariantComparison(
                variant="treatment",
                abs_diff=treatment - control,
                rel_diff=rel,
                ci_low=rel_ci[0] * control,
                ci_high=rel_ci[1] * control,
                rel_ci_low=rel_ci[0],
                rel_ci_high=rel_ci[1],
                p_value=p,
                significant=significant,
                direction=direction,  # type: ignore[arg-type]
            )
        ],
    )


def _power(detectable: float = 0.04, n: int = 15000) -> Power:
    return Power(
        baseline=0.2,
        required_n_per_variant=12000,
        smallest_variant_n=n,
        detectable_effect_now=detectable,
        users_per_day=1300,
        projected_days_to_power=None,
    )


def test_srm_blocks_everything() -> None:
    primary = _readout("add_to_cart_rate", "primary", 0.20, 0.22, rel_ci=(0.05, 0.15), p=1e-6)
    rec = recommend(_spec(), _exposure(mismatch=True), [primary], _power(), AS_OF)
    assert rec.decision == "stop"
    assert "sample ratio" in rec.headline.lower()
    assert [c.passed for c in rec.checks] == [False]


def test_clean_win_ships_with_high_confidence() -> None:
    primary = _readout("add_to_cart_rate", "primary", 0.20, 0.215, rel_ci=(0.045, 0.10), p=1e-6)
    guard = _readout(
        "return_rate", "guardrail", 0.10, 0.101, rel_ci=(-0.05, 0.07), p=0.8, higher_is_better=False
    )
    rec = recommend(_spec(), _exposure(), [primary, guard], _power(), AS_OF)
    assert rec.decision == "ship"
    assert rec.confidence == "high"
    assert not rec.risks


def test_inconclusive_guardrail_downgrades_confidence() -> None:
    primary = _readout("add_to_cart_rate", "primary", 0.20, 0.215, rel_ci=(0.045, 0.10), p=1e-6)
    # Point estimate leans bad and the interval allows +19%: "not significant" is not "safe".
    guard = _readout(
        "return_rate", "guardrail", 0.106, 0.113, rel_ci=(-0.06, 0.19), p=0.3, higher_is_better=False
    )
    rec = recommend(_spec(), _exposure(), [primary, guard], _power(), AS_OF)
    assert rec.decision == "ship"
    assert rec.confidence == "medium"
    assert any("inconclusive" in r for r in rec.risks)
    assert "follow-up" in rec.headline


def test_guardrail_regression_means_iterate() -> None:
    primary = _readout("add_to_cart_rate", "primary", 0.20, 0.215, rel_ci=(0.045, 0.10), p=1e-6)
    guard = _readout(
        "return_rate", "guardrail", 0.10, 0.12, rel_ci=(0.08, 0.32), p=0.001, higher_is_better=False
    )
    rec = recommend(_spec(), _exposure(), [primary, guard], _power(), AS_OF)
    assert rec.decision == "iterate"
    assert "Return rate" in rec.headline


def test_primary_regression_stops() -> None:
    primary = _readout("add_to_cart_rate", "primary", 0.20, 0.185, rel_ci=(-0.12, -0.03), p=0.001)
    rec = recommend(_spec(), _exposure(), [primary], _power(), AS_OF)
    assert rec.decision == "stop"
    assert rec.confidence == "high"


def test_flat_and_powered_stops() -> None:
    primary = _readout("add_to_cart_rate", "primary", 0.20, 0.201, rel_ci=(-0.03, 0.04), p=0.7)
    rec = recommend(_spec(), _exposure(), [primary], _power(detectable=0.035), AS_OF)
    assert rec.decision == "stop"
    assert "no detectable effect" in rec.headline.lower()


def test_flat_and_underpowered_continues_while_running() -> None:
    primary = _readout("add_to_cart_rate", "primary", 0.20, 0.204, rel_ci=(-0.05, 0.09), p=0.5)
    rec = recommend(_spec(end=None), _exposure(n=1500), [primary], _power(detectable=0.08, n=1500), AS_OF)
    assert rec.decision == "continue"
    assert not next(c for c in rec.checks if c.name == "Minimum sample").passed


def test_flat_and_underpowered_after_end_is_inconclusive() -> None:
    primary = _readout("add_to_cart_rate", "primary", 0.20, 0.204, rel_ci=(-0.05, 0.09), p=0.5)
    rec = recommend(_spec(), _exposure(n=1500), [primary], _power(detectable=0.08, n=1500), AS_OF)
    assert rec.decision == "iterate"
    assert "inconclusive" in rec.headline.lower()


def test_early_significance_does_not_ship() -> None:
    primary = _readout("add_to_cart_rate", "primary", 0.20, 0.23, rel_ci=(0.02, 0.28), p=0.03)
    exposure = _exposure(n=800)
    exposure.days_running = 3
    rec = recommend(_spec(end=None), exposure, [primary], _power(detectable=0.12, n=800), AS_OF)
    assert rec.decision == "continue"
    assert any("early" in r.lower() or "peeking" in r.lower() for r in rec.reasons + rec.risks)
