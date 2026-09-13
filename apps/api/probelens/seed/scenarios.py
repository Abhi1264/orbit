"""Single source of truth for the product problems baked into the synthetic data.

Every offset is in days before the dataset's last day, so the same story holds
regardless of when the seed runs. The simulator reads these to bend
probabilities; the Postgres seed reads them to create matching releases and
experiments; docs/data-model.md describes them for humans.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass(frozen=True)
class ReleaseSpec:
    version: str
    name: str
    platform: str
    days_before_end: int
    description: str
    affected_areas: tuple[str, ...]
    # (day offset from release, rollout percent) pairs; last entry holds thereafter.
    rollout: tuple[tuple[int, int], ...] = ((0, 100),)
    status: str = "completed"


@dataclass(frozen=True)
class ExperimentSpec:
    key: str
    name: str
    hypothesis: str
    start_days_before_end: int
    end_days_before_end: int | None
    primary_metric: str
    guardrail_metrics: tuple[str, ...]
    variants: tuple[tuple[str, str, int, bool], ...]  # key, name, weight, is_control
    traffic_percent: int = 100
    # Smallest relative lift on the primary metric worth shipping for; drives the power check.
    min_relative_effect: float = 0.03
    # Simulation effects applied to the treatment variant.
    effects: dict[str, float] = field(default_factory=dict)
    exposure_event: str = "product_view"
    audience_filters: tuple[dict, ...] = ()


@dataclass(frozen=True)
class Scenarios:
    start: date
    end: date

    def day(self, days_before_end: int) -> date:
        return self.end - timedelta(days=days_before_end)

    # --- Scenario 0 (historical, already resolved): footwear sandals sizing ---
    # Lives in the first two weeks of the window so the seeded "resolved"
    # investigation has real evidence behind it.
    historical_spike_subcategory = "sandals"
    historical_spike_multiplier = 1.8

    @property
    def historical_spike_window(self) -> tuple[date, date]:
        return self.start, self.start + timedelta(days=13)

    # --- Scenario 1: Android 8.4.0 payment SDK regression -------------------
    android_release = ReleaseSpec(
        version="8.4.0",
        name="Android 8.4.0 — payment SDK upgrade",
        platform="android",
        days_before_end=20,
        description=(
            "Upgrades the in-app payment SDK to v3 and migrates UPI intent handling to the "
            "new collect-request flow. Also ships wishlist sync improvements."
        ),
        affected_areas=("checkout", "payments", "wishlist"),
        rollout=((0, 20), (2, 50), (4, 100)),
    )
    ios_release = ReleaseSpec(
        version="8.4.0",
        name="iOS 8.4.0 — payment SDK upgrade",
        platform="ios",
        days_before_end=20,
        description="Payment SDK v3 upgrade and wishlist sync improvements, iOS build.",
        affected_areas=("checkout", "payments", "wishlist"),
        rollout=((0, 100),),
    )
    android_hotfix = ReleaseSpec(
        version="8.4.1",
        name="Android 8.4.1 — UPI collect timeout hotfix",
        platform="android",
        days_before_end=-2,
        description="Restores the previous UPI intent flow while SDK v3 collect-request timeouts are investigated.",
        affected_areas=("checkout", "payments"),
        status="planned",
    )
    # Failure multipliers for Android users on 8.4.0 (relative to base failure rate).
    android_upi_failure_multiplier = 5.5
    android_other_failure_multiplier = 1.8

    # --- Scenario 2: Fashion return spike (sizing issue in a supplier batch) --
    return_spike_start_days_before_end = 28
    return_spike_category = "fashion"
    return_spike_subcategory = "dresses"
    return_spike_multiplier = 1.9
    return_spike_reason = "size_fit"

    # --- Scenario 3: Search relevance change hurts footwear click-through -----
    search_release = ReleaseSpec(
        version="search-relevance-v2",
        name="Search relevance v2 — learned ranking",
        platform="all",
        days_before_end=14,
        description="Replaces the hand-tuned BM25 blend with a learned ranker trained on Q2 click data.",
        affected_areas=("search", "discovery"),
    )
    search_ctr_category = "footwear"
    search_ctr_multiplier = 0.68

    # --- Scenario 4: Paid social campaign with poor conversion ---------------
    paid_social_campaign_start_days_before_end = 30
    paid_social_conversion_multiplier = 0.12
    paid_social_bounce_multiplier = 2.0

    # --- Scenario 5: Delivery delays depress repeat purchase -----------------
    delivery_delay_start_days_before_end = 42
    delivery_delay_end_days_before_end = 27
    delivery_delay_city_tier = "tier3"
    delivery_delay_days = (7, 11)
    delayed_user_repurchase_multiplier = 0.55

    # --- Scenario 6: Experiments -------------------------------------------
    experiments = (
        ExperimentSpec(
            key="new_pdp_cta",
            name="New product page CTA",
            hypothesis=(
                "Making Add to Bag more prominent (sticky, high-contrast) on the product page "
                "will increase add-to-cart conversion without hurting purchase quality."
            ),
            start_days_before_end=24,
            end_days_before_end=3,
            primary_metric="add_to_cart_rate",
            guardrail_metrics=("return_rate", "checkout_conversion"),
            variants=(
                ("control", "Existing CTA", 50, True),
                ("treatment", "Sticky high-contrast CTA", 50, False),
            ),
            min_relative_effect=0.05,
            effects={"add_to_cart_rate": 1.08, "return_rate": 1.16},
            exposure_event="product_view",
        ),
        ExperimentSpec(
            key="free_shipping_threshold",
            name="Free shipping threshold nudge",
            hypothesis=(
                "Showing the remaining amount to unlock free shipping at checkout will increase "
                "checkout-to-purchase conversion and average order value."
            ),
            start_days_before_end=42,
            end_days_before_end=12,
            primary_metric="checkout_conversion",
            guardrail_metrics=("return_rate", "aov"),
            variants=(
                ("control", "No nudge", 50, True),
                ("treatment", "Progress bar nudge", 50, False),
            ),
            min_relative_effect=0.04,
            effects={"checkout_conversion": 1.05, "aov": 1.03},
            exposure_event="checkout_started",
        ),
        ExperimentSpec(
            key="search_autocomplete_v2",
            name="Search autocomplete v2",
            hypothesis="Category-aware autocomplete suggestions will lift search-to-product-view rate.",
            start_days_before_end=6,
            end_days_before_end=None,
            primary_metric="search_to_product_view_rate",
            guardrail_metrics=("conversion",),
            variants=(
                ("control", "Current autocomplete", 50, True),
                ("treatment", "Category-aware suggestions", 50, False),
            ),
            traffic_percent=30,
            effects={"search_ctr": 1.03},
            exposure_event="search",
        ),
    )

    web_checkout_release = ReleaseSpec(
        version="web-2026.34",
        name="Web checkout address form redesign",
        platform="web",
        days_before_end=35,
        description="Single-page address entry with pincode autofill.",
        affected_areas=("checkout",),
    )

    @property
    def releases(self) -> tuple[ReleaseSpec, ...]:
        return (
            self.web_checkout_release,
            self.android_release,
            self.ios_release,
            self.search_release,
            self.android_hotfix,
        )

    def rollout_percent(self, release: ReleaseSpec, on: date) -> int:
        offset = (on - self.day(release.days_before_end)).days
        if offset < 0:
            return 0
        pct = 0
        for day_offset, rollout in release.rollout:
            if offset >= day_offset:
                pct = rollout
        return pct
