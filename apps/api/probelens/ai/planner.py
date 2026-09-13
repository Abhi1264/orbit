"""Natural language → structured analytics query, deterministically.

A small grammar rather than a model: metric synonyms, dimension values pulled
from the data itself, relative-date phrases, "by <dimension>" breakdowns and
"vs previous" comparisons. It is fast, testable, works offline, and its
failures are visible (`unresolved` lists the words it could not place) instead
of silently guessing. When an LLM is configured the agent can still call this
as a tool, which keeps the model from inventing filter values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from probelens.analytics.dimensions import DIMENSIONS, Filter
from probelens.analytics.metrics import METRICS

# Longest phrases first so "checkout conversion" wins over "conversion".
METRIC_SYNONYMS: list[tuple[str, str]] = [
    ("checkout conversion", "checkout_conversion"),
    ("checkout to purchase", "checkout_conversion"),
    ("checkout completion", "checkout_conversion"),
    ("add to cart rate", "add_to_cart_rate"),
    ("add-to-cart rate", "add_to_cart_rate"),
    ("add to cart", "add_to_cart_rate"),
    ("add-to-cart", "add_to_cart_rate"),
    ("atc rate", "add_to_cart_rate"),
    ("search to product view", "search_to_product_view_rate"),
    ("search click-through", "search_to_product_view_rate"),
    ("search ctr", "search_to_product_view_rate"),
    ("bounce rate", "bounce_rate"),
    ("bounces", "bounce_rate"),
    ("payment success rate", "payment_success_rate"),
    ("payment success", "payment_success_rate"),
    ("payment failure rate", "payment_failure_rate"),
    ("payment failures", "payment_failures"),
    ("failed payments", "payment_failures"),
    ("payment failure", "payment_failure_rate"),
    ("payment attempts", "payment_attempts"),
    ("payments", "payment_success_rate"),
    ("average order value", "aov"),
    ("order value", "aov"),
    ("basket size", "aov"),
    ("aov", "aov"),
    ("return rate", "return_rate"),
    ("returns", "returns"),
    ("delivery days", "avg_delivery_days"),
    ("delivery time", "avg_delivery_days"),
    ("delivery", "avg_delivery_days"),
    ("product views", "product_views"),
    ("pdp views", "product_views"),
    ("searches", "searches"),
    ("search volume", "searches"),
    ("conversion rate", "conversion"),
    ("conversion", "conversion"),
    ("purchase rate", "conversion"),
    ("cvr", "conversion"),
    ("revenue", "revenue"),
    ("sales", "revenue"),
    ("gmv", "revenue"),
    ("orders", "orders"),
    ("purchases", "orders"),
    ("active users", "users"),
    ("users", "users"),
    ("dau", "users"),
    ("sessions", "sessions"),
    ("visits", "sessions"),
    ("traffic", "sessions"),
]

DIMENSION_SYNONYMS: dict[str, str] = {
    "platform": "platform",
    "os": "platform",
    "device": "device_type",
    "device type": "device_type",
    "app version": "app_version",
    "version": "app_version",
    "release": "app_version",
    "country": "country",
    "city": "city",
    "city tier": "city_tier",
    "tier": "city_tier",
    "traffic source": "traffic_source",
    "source": "traffic_source",
    "channel": "traffic_source",
    "acquisition channel": "traffic_source",
    "user type": "user_type",
    "new vs returning": "user_type",
    "new versus returning": "user_type",
    "category": "category",
    "subcategory": "subcategory",
    "payment method": "payment_method",
    "payment methods": "payment_method",
    "gateway": "payment_gateway",
    "payment gateway": "payment_gateway",
    "failure reason": "failure_reason",
    "return reason": "return_reason",
    "search query": "search_query",
    "query": "search_query",
}

# Dimension values that people say differently from how they are stored.
VALUE_ALIASES: dict[str, tuple[str, str]] = {
    "android": ("platform", "android"),
    "ios": ("platform", "ios"),
    "iphone": ("platform", "ios"),
    "web": ("platform", "web"),
    "desktop": ("device_type", "desktop"),
    "mobile": ("device_type", "mobile"),
    "tablet": ("device_type", "tablet"),
    "india": ("country", "IN"),
    "uae": ("country", "AE"),
    "dubai": ("city", "Dubai"),
    "singapore": ("country", "SG"),
    "tier 1": ("city_tier", "tier1"),
    "tier 2": ("city_tier", "tier2"),
    "tier 3": ("city_tier", "tier3"),
    "tier-1": ("city_tier", "tier1"),
    "tier-2": ("city_tier", "tier2"),
    "tier-3": ("city_tier", "tier3"),
    "paid social": ("traffic_source", "paid_social"),
    "social": ("traffic_source", "paid_social"),
    "paid search": ("traffic_source", "paid_search"),
    "organic": ("traffic_source", "organic"),
    "direct": ("traffic_source", "direct"),
    "email": ("traffic_source", "email"),
    "affiliate": ("traffic_source", "affiliate"),
    "push": ("traffic_source", "push"),
    "new users": ("user_type", "new"),
    "returning users": ("user_type", "returning"),
    "first-time": ("user_type", "new"),
    "upi": ("payment_method", "upi"),
    "card": ("payment_method", "card"),
    "cards": ("payment_method", "card"),
    "cod": ("payment_method", "cod"),
    "cash on delivery": ("payment_method", "cod"),
    "wallet": ("payment_method", "wallet"),
    "netbanking": ("payment_method", "netbanking"),
    "net banking": ("payment_method", "netbanking"),
    "razorpay": ("payment_gateway", "razorpay"),
    "payu": ("payment_gateway", "payu"),
    "paytm": ("payment_gateway", "paytm"),
    "footwear": ("category", "footwear"),
    "shoes": ("category", "footwear"),
    "fashion": ("category", "fashion"),
    "apparel": ("category", "fashion"),
    "beauty": ("category", "beauty"),
    "accessories": ("category", "accessories"),
}

MONTHS = {
    m: i + 1
    for i, m in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ]
    )
}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9

STOPWORDS = {
    "what",
    "whats",
    "what's",
    "how",
    "is",
    "are",
    "was",
    "were",
    "the",
    "a",
    "an",
    "of",
    "for",
    "in",
    "on",
    "did",
    "does",
    "do",
    "show",
    "me",
    "give",
    "get",
    "please",
    "and",
    "to",
    "with",
    "our",
    "my",
    "we",
    "us",
    "it",
    "rate",
    "vs",
    "versus",
    "compared",
    "compare",
    "against",
    "over",
    "time",
    "trend",
    "trends",
    "daily",
    "weekly",
    "monthly",
    "by",
    "per",
    "across",
    "break",
    "down",
    "breakdown",
    "split",
    "why",
    "fall",
    "fell",
    "drop",
    "dropped",
    "decline",
    "declined",
    "rise",
    "rose",
    "increase",
    "increased",
    "up",
    "change",
    "changed",
    "last",
    "this",
    "previous",
    "prior",
    "week",
    "weeks",
    "day",
    "days",
    "month",
    "months",
    "yesterday",
    "today",
    "recent",
    "recently",
    "period",
    "since",
    "from",
    "between",
    "until",
    "till",
    "through",
    "so",
    "far",
    "look",
    "like",
    "at",
    "number",
    "many",
    "much",
    "happening",
    "going",
    "doing",
    "performing",
    "performance",
    "should",
    "ship",
    "experiment",
    "test",
    "results",
    "result",
    "where",
    "users",
    "user",
    "sessions",
    "session",
    "store",
    "wide",
    "overall",
    "total",
    "all",
    "funnel",
    "funnels",
    "attention",
    "needs",
    "need",
    "right",
    "now",
    "anything",
    "wrong",
    "off",
    "unusual",
    "anomalies",
    "anomaly",
    "running",
    "currently",
    "which",
    "any",
}

Intent = Literal["why", "what", "funnel", "experiment", "attention", "compare"]


@dataclass
class ParsedDates:
    date_from: date
    date_to: date
    explicit: bool
    compare: bool = False
    granularity: Literal["hour", "day", "week", "month"] = "day"
    phrase: str = ""


@dataclass
class Plan:
    metric: str | None
    filters: list[Filter]
    breakdown: str | None
    dates: ParsedDates
    unresolved: list[str] = field(default_factory=list)
    matched: list[str] = field(default_factory=list)
    intent: Intent = "what"
    experiment_hint: str | None = None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("’", "'")).strip()


def parse_dates(text: str, today: date, default_days: int = 14) -> ParsedDates:
    """Relative and absolute date phrases → window. Defaults to the last `default_days`."""
    t = _norm(text)
    compare = bool(
        re.search(
            r"\b(vs|versus|compared? (to|with)|against|change|changed|fell|fall|drop|rose|rise|why)\b", t
        )
    )
    granularity: Literal["hour", "day", "week", "month"] = "day"
    if re.search(r"\b(weekly|by week|per week)\b", t):
        granularity = "week"
    if re.search(r"\b(monthly|by month|per month)\b", t):
        granularity = "month"
    if re.search(r"\b(hourly|by hour|per hour)\b", t):
        granularity = "hour"

    m = re.search(r"\b(last|past|previous|trailing)\s+(\d+)\s+(day|days|week|weeks|month|months)\b", t)
    if m:
        n = int(m.group(2))
        unit = m.group(3)
        days = n * (7 if unit.startswith("week") else 30 if unit.startswith("month") else 1)
        return ParsedDates(today - timedelta(days=days - 1), today, True, compare, granularity, m.group(0))
    if re.search(r"\byesterday\b", t):
        return ParsedDates(
            today - timedelta(days=1), today - timedelta(days=1), True, compare, "hour", "yesterday"
        )
    if re.search(r"\btoday\b", t):
        return ParsedDates(today, today, True, compare, "hour", "today")
    if re.search(r"\blast week\b", t):
        # Calendar week, Monday–Sunday, immediately before the current one.
        this_monday = today - timedelta(days=today.weekday())
        return ParsedDates(
            this_monday - timedelta(days=7),
            this_monday - timedelta(days=1),
            True,
            compare,
            "day",
            "last week",
        )
    if re.search(r"\bthis week\b", t):
        this_monday = today - timedelta(days=today.weekday())
        return ParsedDates(this_monday, today, True, compare, "day", "this week")
    if re.search(r"\blast month\b", t):
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return ParsedDates(last_prev.replace(day=1), last_prev, True, compare, "day", "last month")
    if re.search(r"\bthis month\b|\bmonth to date\b|\bmtd\b", t):
        return ParsedDates(today.replace(day=1), today, True, compare, "day", "this month")
    if re.search(r"\b(last|past) (\d+ )?fortnight\b", t):
        return ParsedDates(today - timedelta(days=13), today, True, compare, "day", "last fortnight")
    if re.search(r"\b(last|past|this) quarter\b|\bqtd\b", t):
        q_start = date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
        return ParsedDates(q_start, today, True, compare, "week", "this quarter")

    # "in September", "September 1 to 10", "since 5 Sep", "between 1 and 10 sept"
    month_m = re.search(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b", t)
    if month_m:
        month = MONTHS[month_m.group(1)]
        year = today.year if month <= today.month else today.year - 1
        nums = [int(x) for x in re.findall(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", t) if 1 <= int(x) <= 31]
        if re.search(r"\bsince\b", t) and nums:
            return ParsedDates(
                date(year, month, nums[0]), today, True, compare, granularity, month_m.group(0)
            )
        if len(nums) >= 2:
            a, b = sorted(nums[:2])
            return ParsedDates(
                date(year, month, a),
                min(date(year, month, b), today),
                True,
                compare,
                granularity,
                month_m.group(0),
            )
        if len(nums) == 1:
            d = date(year, month, nums[0])
            return ParsedDates(d, d, True, compare, "hour", month_m.group(0))
        start = date(year, month, 1)
        end = (start.replace(month=month + 1) if month < 12 else date(year + 1, 1, 1)) - timedelta(days=1)
        return ParsedDates(start, min(end, today), True, compare, granularity, month_m.group(0))

    iso = re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", t)
    if len(iso) >= 2:
        a, b = sorted(date.fromisoformat(x) for x in iso[:2])
        return ParsedDates(a, b, True, compare, granularity, " to ".join(iso[:2]))
    if len(iso) == 1:
        d = date.fromisoformat(iso[0])
        if re.search(r"\bsince\b", t):
            return ParsedDates(d, today, True, compare, granularity, f"since {iso[0]}")
        return ParsedDates(d, d, True, compare, "hour", iso[0])

    return ParsedDates(today - timedelta(days=default_days - 1), today, False, compare, granularity, "")


def parse_metric(text: str) -> tuple[str | None, str | None]:
    """(metric_key, matched phrase)."""
    t = _norm(text)
    for phrase, key in METRIC_SYNONYMS:
        if re.search(rf"\b{re.escape(phrase)}\b", t):
            return key, phrase
    for key, m in METRICS.items():
        if re.search(rf"\b{re.escape(m.label.lower())}\b", t):
            return key, m.label.lower()
    return None, None


def parse_breakdown(text: str) -> tuple[str | None, str | None]:
    t = _norm(text)
    m = re.search(
        r"\b(?:by|per|across|split by|broken down by|breakdown by|for each)\s+([a-z][a-z ]{1,25})", t
    )
    if not m:
        return None, None
    tail = m.group(1)
    for phrase in sorted(DIMENSION_SYNONYMS, key=len, reverse=True):
        if tail.startswith(phrase):
            return DIMENSION_SYNONYMS[phrase], f"by {phrase}"
    return None, None


def parse_filters(text: str, values: dict[str, list[str]] | None = None) -> tuple[list[Filter], list[str]]:
    """Dimension values mentioned anywhere in the text. Same-dimension mentions
    collapse to an `in` filter ("android and ios")."""
    t = _norm(text)
    hits: dict[str, list[str]] = {}
    matched: list[str] = []
    for phrase in sorted(VALUE_ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(phrase)}\b", t):
            dim, val = VALUE_ALIASES[phrase]
            if val not in hits.setdefault(dim, []):
                hits[dim].append(val)
            matched.append(phrase)
            t = re.sub(rf"\b{re.escape(phrase)}\b", " ", t)
    # Raw values from the data (cities, subcategories, versions, failure reasons…).
    for dim, vals in (values or {}).items():
        if dim in ("platform", "device_type", "country", "search_query"):
            continue
        for v in vals:
            token = str(v).lower().replace("_", " ")
            if len(token) < 3:
                continue
            if re.search(rf"\b{re.escape(token)}\b", t):
                if str(v) not in hits.setdefault(dim, []):
                    hits[dim].append(str(v))
                matched.append(token)
                t = re.sub(rf"\b{re.escape(token)}\b", " ", t)
    filters: list[Filter] = []
    for dim, vals in hits.items():
        if dim not in DIMENSIONS:
            continue
        if len(vals) == 1:
            filters.append(Filter(dimension=dim, operator="eq", value=vals[0]))
        else:
            filters.append(Filter(dimension=dim, operator="in", values=vals))
    return filters, matched


def detect_intent(text: str) -> Intent:
    t = _norm(text)
    if re.search(r"\b(why|what happened|what caused|cause|reason|explain|root cause|driving|drove)\b", t):
        return "why"
    if re.search(r"\b(experiment|a/b|ab test|variant|treatment|should we ship|ship it|readout)\b", t):
        return "experiment"
    if re.search(
        r"\b(funnel|drop[- ]?off|drop off|where do (users|people) (drop|leave|abandon)|abandon)\b", t
    ):
        return "funnel"
    if re.search(
        r"\b(anomal|unusual|attention|alerts?|what('s| is) (wrong|off|broken)|needs? (a )?look"
        r"|anything (off|wrong|unusual))",
        t,
    ):
        return "attention"
    if re.search(r"\b(vs|versus|compare|compared|against|difference between)\b", t):
        return "compare"
    return "what"


def parse(text: str, today: date, values: dict[str, list[str]] | None = None, default_days: int = 14) -> Plan:
    metric, mphrase = parse_metric(text)
    filters, fmatched = parse_filters(text, values)
    breakdown, bphrase = parse_breakdown(text)
    dates = parse_dates(text, today, default_days)
    intent = detect_intent(text)

    # "android vs ios": a comparison of two values on one dimension is a breakdown, not a filter.
    if intent == "compare" and breakdown is None:
        for f in filters:
            if f.operator == "in" and f.values and len(f.values) == 2:
                breakdown = f.dimension
                filters = [x for x in filters if x is not f] + [f]  # keep filter to restrict to the two
                break

    matched = [p for p in [mphrase, bphrase, dates.phrase, *fmatched] if p]
    leftover = _norm(text)
    for p in matched:
        leftover = re.sub(rf"\b{re.escape(p)}\b", " ", leftover)
    tokens = [w for w in re.findall(r"[a-z][a-z\-']+", leftover) if w not in STOPWORDS and len(w) > 2]
    exp_hint = None
    m = re.search(r"\b(?:experiment|test)\s+([a-z0-9_ ]{3,40})", _norm(text))
    if m:
        exp_hint = m.group(1).strip()
    return Plan(
        metric=metric,
        filters=filters,
        breakdown=breakdown,
        dates=dates,
        unresolved=sorted(set(tokens)),
        matched=matched,
        intent=intent,
        experiment_hint=exp_hint,
    )


def previous_window(date_from: date, date_to: date) -> tuple[date, date]:
    days = (date_to - date_from).days + 1
    return date_from - timedelta(days=days), date_from - timedelta(days=1)


def describe(plan: Plan) -> str:
    parts: list[str] = []
    if plan.metric:
        parts.append(METRICS[plan.metric].label)
    if plan.filters:
        parts.append(", ".join(f.describe() for f in plan.filters))
    d = plan.dates
    parts.append(
        f"{d.date_from:%-d %b} – {d.date_to:%-d %b}" if d.date_from != d.date_to else f"{d.date_from:%-d %b}"
    )
    if plan.breakdown:
        parts.append(f"by {DIMENSIONS[plan.breakdown].label.lower()}")
    if d.compare:
        parts.append("vs previous period")
    return " · ".join(parts)
