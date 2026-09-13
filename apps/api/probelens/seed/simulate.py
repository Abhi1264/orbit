"""Session-level behavioural simulator.

Each active user-day produces one session that walks the funnel with
probabilities bent by user traits and by the scenarios in `scenarios.py`. The
output is a flat list of event rows in `EVENT_COLUMNS` order, ready for
ClickHouse. Everything draws from one seeded `random.Random`, so a given
(seed, profile, end date) always yields the same dataset.
"""

import random
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta

from probelens.experiments.assignment import VariantSpec, assign
from probelens.seed.catalog import CATEGORIES, SEARCH_QUERIES, ProductRow
from probelens.seed.population import PAYMENT_METHODS, TRAFFIC_SOURCES, SimUser, weighted_choice
from probelens.seed.scenarios import ExperimentSpec, Scenarios

EVENT_COLUMNS = [
    "event_id",
    "event_name",
    "timestamp",
    "user_id",
    "session_id",
    "platform",
    "device_type",
    "app_version",
    "country",
    "city",
    "city_tier",
    "traffic_source",
    "user_type",
    "experiments",
    "product_id",
    "category",
    "subcategory",
    "order_id",
    "order_value",
    "payment_method",
    "payment_gateway",
    "failure_reason",
    "return_reason",
    "search_query",
    "delivery_days",
    "properties",
]

# Relative hourly traffic: quiet overnight, lunchtime bump, evening peak.
_HOUR_WEIGHTS = [
    1,
    0.6,
    0.4,
    0.3,
    0.3,
    0.5,
    1,
    2,
    3,
    3.5,
    3.8,
    4,
    4.2,
    4,
    3.6,
    3.5,
    3.8,
    4.5,
    5.5,
    6.5,
    7,
    6.5,
    5,
    3,
]
_DOW_FACTOR = [1.0, 0.96, 0.95, 0.97, 1.02, 1.12, 1.18]  # Mon..Sun

_BASE_FAIL = {"upi": 0.045, "card": 0.06, "cod": 0.01, "wallet": 0.04, "netbanking": 0.085}
_FAIL_REASONS = {
    "upi": [
        ("user_cancelled", 0.35),
        ("gateway_timeout", 0.25),
        ("bank_declined", 0.25),
        ("otp_failed", 0.15),
    ],
    "card": [
        ("bank_declined", 0.4),
        ("otp_failed", 0.3),
        ("insufficient_funds", 0.2),
        ("gateway_timeout", 0.1),
    ],
    "cod": [("user_cancelled", 1.0)],
    "wallet": [("insufficient_funds", 0.6), ("gateway_timeout", 0.4)],
    "netbanking": [("gateway_timeout", 0.5), ("bank_declined", 0.3), ("user_cancelled", 0.2)],
}
_GATEWAYS = {
    "upi": "payu",
    "card": "razorpay",
    "cod": "",
    "wallet": "paytm",
    "netbanking": "razorpay",
}

class Simulator:
    def __init__(
        self,
        rng: random.Random,
        users: list[SimUser],
        products: list[ProductRow],
        start: date,
        end: date,
        scenarios: Scenarios,
    ) -> None:
        self.rng = rng
        self.users = users
        self.start = start
        self.end = end
        self.sc = scenarios
        self.products_by_id = {p.id: p for p in products}
        self.by_category: dict[str, tuple[list[ProductRow], list[float]]] = {}
        for cat in CATEGORIES:
            items = [p for p in products if p.category == cat]
            cum, acc = [], 0.0
            for p in items:
                acc += p.popularity
                cum.append(acc)
            self.by_category[cat] = (items, cum)
        self.order_seq = 0
        self.variant_specs = {
            e.key: [VariantSpec(k, w) for k, _, w, _ in e.variants] for e in scenarios.experiments
        }
        self.exp_windows = {
            e.key: (
                scenarios.day(e.start_days_before_end),
                scenarios.day(e.end_days_before_end) if e.end_days_before_end is not None else end,
            )
            for e in scenarios.experiments
        }
        self.exp_by_exposure: dict[str, list[ExperimentSpec]] = {}
        for e in scenarios.experiments:
            self.exp_by_exposure.setdefault(e.exposure_event, []).append(e)

    def _uuid(self) -> str:
        return str(uuid.UUID(int=self.rng.getrandbits(128), version=4))

    def _pick_product(self, user: SimUser) -> ProductRow:
        cats = list(CATEGORIES)
        weights = [CATEGORIES[c]["share"] * user.category_affinity[c] for c in cats]
        cat = self.rng.choices(cats, weights=weights, k=1)[0]
        items, cum = self.by_category[cat]
        return self.rng.choices(items, cum_weights=cum, k=1)[0]

    def _app_version(self, user: SimUser, day: date) -> str:
        if user.platform == "web":
            return ""
        release = self.sc.android_release if user.platform == "android" else self.sc.ios_release
        rollout = self.sc.rollout_percent(release, day)
        released_on = self.sc.day(release.days_before_end)
        if (
            rollout
            and user.update_bucket < rollout
            and day >= released_on + timedelta(days=user.update_delay_days)
        ):
            return release.version
        return user.version_before

    def _active_experiments(self, user: SimUser, day: date, exposure_event: str) -> dict[str, str]:
        out = {}
        for e in self.exp_by_exposure.get(exposure_event, ()):
            start, end = self.exp_windows[e.key]
            if not (start <= day <= end):
                continue
            variant = assign(e.key, user.id, self.variant_specs[e.key], e.traffic_percent)
            if variant:
                out[e.key] = variant
        return out

    def _effect(self, exposures: dict[str, str], metric: str) -> float:
        mult = 1.0
        for e in self.sc.experiments:
            if exposures.get(e.key) == "treatment":
                mult *= e.effects.get(metric, 1.0)
        return mult

    def run(self, on_progress: Callable[[date, int], None] | None = None) -> Iterator[list[tuple]]:
        """Yield batches of event rows, one batch per simulated day."""
        day = self.start
        while day <= self.end:
            rows: list[tuple] = []
            dow = _DOW_FACTOR[day.weekday()]
            campaign_live = day >= self.sc.day(self.sc.paid_social_campaign_start_days_before_end)
            for user in self.users:
                if user.signup_date > day:
                    continue
                is_signup_day = user.signup_date == day
                if is_signup_day or self.rng.random() < user.activity * dow:
                    self._session(rows, user, day, is_signup_day, forced_source=None)
                # Retargeting leg of the campaign: existing customers see the ads too and
                # convert normally. The damage comes from who the ads *acquire*.
                if campaign_live and not user.campaign_acquired and self.rng.random() < 0.005:
                    self._session(rows, user, day, False, forced_source="paid_social")
            if on_progress:
                on_progress(day, len(rows))
            yield rows
            day += timedelta(days=1)

    def _session(
        self, rows: list[tuple], user: SimUser, day: date, is_new: bool, forced_source: str | None
    ) -> None:
        rng = self.rng
        sc = self.sc
        hour = rng.choices(range(24), weights=_HOUR_WEIGHTS, k=1)[0]
        ts = datetime(day.year, day.month, day.day, hour, rng.randint(0, 59), rng.randint(0, 59), tzinfo=UTC)
        session_id = rng.getrandbits(63)
        if forced_source:
            source = forced_source
        elif is_new or rng.random() < 0.55:
            source = user.acquisition_source  # first session is by definition the acquiring channel
        else:
            source = weighted_choice(rng, TRAFFIC_SOURCES)
        app_version = self._app_version(user, day)
        user_type = "new" if is_new else "returning"
        exposures: dict[str, str] = {}

        intent = user.intent
        if user.delivery_delayed:
            intent *= sc.delayed_user_repurchase_multiplier
        low_intent_campaign = user.campaign_acquired
        if low_intent_campaign:
            intent *= sc.paid_social_conversion_multiplier

        def emit(name: str, **kw) -> None:
            nonlocal ts
            ts += timedelta(seconds=rng.randint(4, 75))
            if kw.get("timestamp", ts).date() > self.end:
                return
            rows.append(
                (
                    self._uuid(),
                    name,
                    kw.get("timestamp", ts),
                    user.id,
                    session_id,
                    user.platform,
                    user.device_type,
                    app_version,
                    user.country,
                    user.city,
                    user.city_tier,
                    source,
                    user_type,
                    dict(exposures),
                    kw.get("product_id", 0),
                    kw.get("category", ""),
                    kw.get("subcategory", ""),
                    kw.get("order_id", 0),
                    kw.get("order_value", 0.0),
                    kw.get("payment_method", ""),
                    kw.get("payment_gateway", ""),
                    kw.get("failure_reason", ""),
                    kw.get("return_reason", ""),
                    kw.get("search_query", ""),
                    kw.get("delivery_days", 0),
                    kw.get("properties", ""),
                )
            )

        deep_link = source in ("paid_social", "paid_search", "push", "email") and rng.random() < 0.4
        if not deep_link:
            emit("home_view")

        # Bounce: campaign traffic bounces more, even when deep-linked to a product.
        bounce_p = 0.28 * (sc.paid_social_bounce_multiplier if low_intent_campaign else 1.0)
        if (not deep_link or low_intent_campaign) and rng.random() < bounce_p:
            if deep_link:
                p = self._pick_product(user)
                emit("product_view", product_id=p.id, category=p.category, subcategory=p.subcategory)
            return

        viewed: list[ProductRow] = []
        searched = not deep_link and rng.random() < (0.5 if user.platform == "web" else 0.42)
        if searched:
            exposures.update(self._active_experiments(user, day, "search"))
            cats = list(CATEGORIES)
            cat = rng.choices(cats, weights=[user.category_affinity[c] for c in cats], k=1)[0]
            query = rng.choice(SEARCH_QUERIES[cat])
            emit("search", search_query=query, category=cat)
            if rng.random() < 0.96:
                emit("search_result_view", search_query=query, category=cat)
                ctr = 0.58 * self._effect(exposures, "search_ctr")
                if cat == sc.search_ctr_category and day >= sc.day(sc.search_release.days_before_end):
                    ctr *= sc.search_ctr_multiplier
                if rng.random() < ctr:
                    items, cum = self.by_category[cat]
                    viewed.append(rng.choices(items, cum_weights=cum, k=1)[0])
                elif rng.random() < 0.55:
                    return
            else:
                return

        n_views = len(viewed) + (1 if deep_link else 0) + int(rng.expovariate(1 / 1.4))
        if searched and not viewed and rng.random() < 0.35:
            n_views = 0
        while len(viewed) < n_views:
            viewed.append(self._pick_product(user))
        if not viewed:
            return

        for p in viewed:
            exposures.update(self._active_experiments(user, day, "product_view"))
            emit("product_view", product_id=p.id, category=p.category, subcategory=p.subcategory)
            if rng.random() < 0.07:
                emit(
                    "add_to_wishlist",
                    product_id=p.id,
                    category=p.category,
                    subcategory=p.subcategory,
                )

        atc_p = min(0.9, 0.15 * intent * self._effect(exposures, "add_to_cart_rate"))
        cart: list[ProductRow] = []
        for i, p in enumerate(viewed):
            if rng.random() < (atc_p if i == 0 else atc_p * 0.45):
                cart.append(p)
                emit("add_to_cart", product_id=p.id, category=p.category, subcategory=p.subcategory)
        if not cart:
            return

        if rng.random() > 0.55 * min(1.4, intent**0.5):
            return
        exposures.update(self._active_experiments(user, day, "checkout_started"))
        emit("checkout_started", order_value=sum(p.price for p in cart))

        if rng.random() > min(0.95, 0.72 * self._effect(exposures, "checkout_conversion")):
            return

        method = user.payment_method if rng.random() < 0.85 else weighted_choice(rng, PAYMENT_METHODS)
        gateway = _GATEWAYS[method]
        fail_p = _BASE_FAIL[method]
        on_bad_build = (
            user.platform == "android"
            and app_version == sc.android_release.version
            and day >= sc.day(sc.android_release.days_before_end)
        )
        if on_bad_build:
            fail_p *= (
                sc.android_upi_failure_multiplier if method == "upi" else sc.android_other_failure_multiplier
            )
        fail_p = min(fail_p, 0.6)

        paid = False
        for attempt in range(2):
            emit(
                "payment_started",
                payment_method=method,
                payment_gateway=gateway,
                order_value=sum(p.price for p in cart),
            )
            if rng.random() < fail_p:
                if on_bad_build and rng.random() < 0.7:
                    reason = "gateway_timeout"
                else:
                    reason = weighted_choice(rng, _FAIL_REASONS[method])
                emit(
                    "payment_failed",
                    payment_method=method,
                    payment_gateway=gateway,
                    failure_reason=reason,
                )
                if attempt == 0 and rng.random() < 0.42:
                    fail_p *= 0.75
                    continue
                return
            paid = True
            break
        if not paid:
            return

        self.order_seq += 1
        order_id = self.order_seq
        aov_mult = self._effect(exposures, "aov")
        emit(
            "payment_success",
            payment_method=method,
            payment_gateway=gateway,
            order_id=order_id,
            order_value=round(sum(p.price for p in cart) * aov_mult, 2),
        )

        delayed = user.city_tier == sc.delivery_delay_city_tier and sc.day(
            sc.delivery_delay_start_days_before_end
        ) <= day <= sc.day(sc.delivery_delay_end_days_before_end)
        if delayed:
            delivery_days = rng.randint(*sc.delivery_delay_days)
        else:
            delivery_days = rng.choice([2, 3, 3, 4, 4, 5]) + (2 if user.city_tier == "tier3" else 0)
        order_ts = ts
        for p in cart:
            value = round(p.price * aov_mult * rng.uniform(0.9, 1.0), 2)
            emit(
                "order_completed",
                product_id=p.id,
                category=p.category,
                subcategory=p.subcategory,
                order_id=order_id,
                order_value=value,
                payment_method=method,
                delivery_days=delivery_days,
            )
            delivered_at = order_ts + timedelta(days=delivery_days, hours=rng.randint(9, 20))
            if delivered_at.date() <= self.end:
                emit(
                    "delivery_completed",
                    payment_method=method,
                    timestamp=delivered_at,
                    product_id=p.id,
                    category=p.category,
                    subcategory=p.subcategory,
                    order_id=order_id,
                    order_value=value,
                    delivery_days=delivery_days,
                )
                return_p = CATEGORIES[p.category]["return_rate"] * self._effect(exposures, "return_rate")
                if (
                    p.category == sc.return_spike_category
                    and p.subcategory == sc.return_spike_subcategory
                    and day >= sc.day(sc.return_spike_start_days_before_end)
                ):
                    return_p *= sc.return_spike_multiplier
                    reason = sc.return_spike_reason if rng.random() < 0.7 else "changed_mind"
                elif (
                    p.subcategory == sc.historical_spike_subcategory
                    and sc.historical_spike_window[0] <= day <= sc.historical_spike_window[1]
                ):
                    return_p *= sc.historical_spike_multiplier
                    reason = "size_fit" if rng.random() < 0.75 else "changed_mind"
                else:
                    reason = weighted_choice(
                        rng,
                        [
                            ("size_fit", 0.4),
                            ("changed_mind", 0.3),
                            ("quality", 0.2),
                            ("wrong_item", 0.1),
                        ],
                    )
                if rng.random() < return_p:
                    initiated = delivered_at + timedelta(days=rng.randint(1, 9), hours=rng.randint(1, 10))
                    if initiated.date() <= self.end:
                        emit(
                            "return_initiated",
                            payment_method=method,
                            timestamp=initiated,
                            product_id=p.id,
                            category=p.category,
                            subcategory=p.subcategory,
                            order_id=order_id,
                            order_value=value,
                            return_reason=reason,
                        )
                        completed = initiated + timedelta(days=rng.randint(3, 7))
                        if completed.date() <= self.end:
                            emit(
                                "return_completed",
                                payment_method=method,
                                timestamp=completed,
                                product_id=p.id,
                                category=p.category,
                                subcategory=p.subcategory,
                                order_id=order_id,
                                order_value=value,
                            )

        user.orders += 1
        if user.first_purchase_date is None:
            user.first_purchase_date = day
        if delayed:
            user.delivery_delayed = True
