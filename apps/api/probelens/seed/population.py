import random
from dataclasses import dataclass, field
from datetime import date, timedelta

CITIES: list[tuple[str, str, str, float]] = [
    # city, tier, country, weight
    ("Mumbai", "tier1", "IN", 12),
    ("Delhi", "tier1", "IN", 12),
    ("Bengaluru", "tier1", "IN", 11),
    ("Hyderabad", "tier1", "IN", 7),
    ("Chennai", "tier1", "IN", 6),
    ("Pune", "tier1", "IN", 6),
    ("Kolkata", "tier1", "IN", 5),
    ("Ahmedabad", "tier2", "IN", 4),
    ("Jaipur", "tier2", "IN", 4),
    ("Lucknow", "tier2", "IN", 3.5),
    ("Surat", "tier2", "IN", 3),
    ("Indore", "tier2", "IN", 3),
    ("Chandigarh", "tier2", "IN", 2.5),
    ("Kochi", "tier2", "IN", 2.5),
    ("Bhopal", "tier2", "IN", 2),
    ("Nagpur", "tier2", "IN", 2),
    ("Patna", "tier3", "IN", 2),
    ("Guwahati", "tier3", "IN", 1.5),
    ("Ranchi", "tier3", "IN", 1.5),
    ("Raipur", "tier3", "IN", 1.3),
    ("Dehradun", "tier3", "IN", 1.2),
    ("Siliguri", "tier3", "IN", 1.0),
    ("Jamshedpur", "tier3", "IN", 1.0),
    ("Dubai", "tier1", "AE", 2.5),
    ("Singapore", "tier1", "SG", 1.5),
]

PLATFORMS = [("android", 0.56), ("ios", 0.24), ("web", 0.20)]
TRAFFIC_SOURCES = [
    ("organic", 0.30),
    ("direct", 0.24),
    ("paid_search", 0.14),
    ("paid_social", 0.12),
    ("email", 0.08),
    ("push", 0.07),
    ("affiliate", 0.05),
]
PAYMENT_METHODS = [
    ("upi", 0.48),
    ("card", 0.25),
    ("cod", 0.17),
    ("wallet", 0.06),
    ("netbanking", 0.04),
]
ANDROID_VERSIONS_BEFORE = [("8.3.1", 0.62), ("8.3.0", 0.28), ("8.2.0", 0.10)]
IOS_VERSIONS_BEFORE = [("8.3.1", 0.75), ("8.3.0", 0.25)]


def weighted_choice(rng: random.Random, options: list[tuple]) -> str:
    r = rng.random() * sum(w for _, w, *_ in options)
    acc = 0.0
    for opt in options:
        acc += opt[1]
        if r <= acc:
            return opt[0]
    return options[-1][0]


@dataclass
class SimUser:
    id: int
    signup_date: date
    platform: str
    device_type: str
    country: str
    city: str
    city_tier: str
    acquisition_source: str
    payment_method: str
    activity: float  # expected sessions per day
    intent: float  # multiplier on purchase propensity
    category_affinity: dict[str, float]
    version_before: str
    update_delay_days: int
    update_bucket: int  # 0-99, gates staged rollout
    first_purchase_date: date | None = None
    delivery_delayed: bool = False
    orders: int = 0
    session_seq: int = field(default=0)


def generate_users(rng: random.Random, count: int, start: date, end: date) -> list[SimUser]:
    users: list[SimUser] = []
    window_days = (end - start).days + 1
    city_weights = [c[3] for c in CITIES]
    for uid in range(1, count + 1):
        # ~12% of users sign up inside the window (they appear as "new" on their first day).
        if rng.random() < 0.12:
            signup = start + timedelta(days=int(rng.random() ** 1.1 * window_days))
        else:
            signup = start - timedelta(days=rng.randint(1, 540))
        platform = weighted_choice(rng, PLATFORMS)
        device = "desktop" if platform == "web" and rng.random() < 0.55 else "mobile"
        if platform != "web" and rng.random() < 0.06:
            device = "tablet"
        city, tier, country, _ = rng.choices(CITIES, weights=city_weights, k=1)[0]
        affinity = {
            "fashion": rng.uniform(0.6, 1.4),
            "footwear": rng.uniform(0.4, 1.3),
            "accessories": rng.uniform(0.4, 1.3),
            "beauty": rng.uniform(0.3, 1.5),
        }
        if platform == "android":
            version_before = weighted_choice(rng, ANDROID_VERSIONS_BEFORE)
        elif platform == "ios":
            version_before = weighted_choice(rng, IOS_VERSIONS_BEFORE)
        else:
            version_before = ""
        users.append(
            SimUser(
                id=uid,
                signup_date=signup,
                platform=platform,
                device_type=device,
                country=country,
                city=city,
                city_tier=tier,
                acquisition_source=weighted_choice(rng, TRAFFIC_SOURCES),
                payment_method=weighted_choice(rng, PAYMENT_METHODS) if country == "IN" else "card",
                activity=min(1.0, rng.lognormvariate(-1.75, 0.75)),
                intent=rng.lognormvariate(0, 0.45),
                category_affinity=affinity,
                version_before=version_before,
                update_delay_days=int(rng.expovariate(1 / 3.0)),
                update_bucket=rng.randint(0, 99),
            )
        )
    return users
