"""The natural-language planner is deterministic; these pin the phrasing it must understand."""

from datetime import date

from probelens.ai import planner

TODAY = date(2026, 9, 13)  # a Sunday
VALUES = {
    "platform": ["android", "ios", "web"],
    "traffic_source": ["organic", "paid_social", "paid_search", "direct", "email", "push"],
    "payment_method": ["upi", "card", "cod", "wallet", "netbanking"],
    "category": ["footwear", "apparel", "accessories"],
    "city_tier": ["tier1", "tier2", "tier3"],
}


def _plan(text: str) -> planner.Plan:
    return planner.parse(text, TODAY, VALUES)


def test_why_question_maps_metric_dates_and_intent() -> None:
    p = _plan("Why did conversion fall last week?")
    assert p.intent == "why"
    assert p.metric == "conversion"
    # "last week" is the previous Monday–Sunday.
    assert (p.dates.date_from, p.dates.date_to) == (date(2026, 8, 31), date(2026, 9, 6))
    assert p.dates.explicit
    assert p.unresolved == []


def test_filters_come_from_known_dimension_values() -> None:
    p = _plan("payment success rate on android for upi last 30 days")
    assert p.metric == "payment_success_rate"
    dims = {(f.dimension, f.value) for f in p.filters}
    assert dims == {("platform", "android"), ("payment_method", "upi")}
    assert (p.dates.date_from, p.dates.date_to) == (date(2026, 8, 15), TODAY)


def test_breakdown_phrasing() -> None:
    for text in (
        "conversion by traffic source",
        "conversion split by traffic source",
        "conversion per channel",
    ):
        p = _plan(text)
        assert p.breakdown == "traffic_source", text


def test_two_values_on_one_dimension_becomes_a_comparison() -> None:
    p = _plan("android vs ios conversion this week")
    assert p.intent == "compare"
    assert p.breakdown == "platform"
    assert p.filters[0].operator == "in"
    assert set(p.filters[0].values or []) == {"android", "ios"}


def test_month_names_and_ranges() -> None:
    p = _plan("revenue in august")
    assert p.metric == "revenue"
    assert (p.dates.date_from, p.dates.date_to) == (date(2026, 8, 1), date(2026, 8, 31))
    p = _plan("orders from 1 sep to 10 sep")
    assert (p.dates.date_from, p.dates.date_to) == (date(2026, 9, 1), date(2026, 9, 10))


def test_intents() -> None:
    assert _plan("what needs attention right now?").intent == "attention"
    assert _plan("show the checkout funnel by platform").intent == "funnel"
    assert _plan("how is the new pdp cta experiment doing").intent == "experiment"
    assert _plan("add to cart rate yesterday").intent == "what"


def test_unresolved_words_are_reported_not_guessed() -> None:
    p = _plan("conversion for wholesale customers last week")
    assert p.metric == "conversion"
    assert "wholesale" in p.unresolved
    assert p.filters == []


def test_describe_is_human_readable() -> None:
    p = _plan("payment failure rate on ios by payment method last 7 days")
    text = planner.describe(p)
    assert "Payment failure rate" in text
    assert "Platform = ios" in text
    assert "by payment method" in text.lower()


def test_previous_window_is_adjacent_and_same_length() -> None:
    a, b = planner.previous_window(date(2026, 9, 1), date(2026, 9, 7))
    assert (a, b) == (date(2026, 8, 25), date(2026, 8, 31))
