"""Deterministic experiment assignment.

A user's bucket is derived from MD5(experiment_key:user_id), so the same user
always lands in the same variant, in Python and in ClickHouse alike. The SQL
equivalent lives in `bucket_sql()` and is verified against this implementation
by tests, which is what lets app-created experiments be analysed retroactively
on the event stream without ever storing assignments.
"""

import hashlib
from dataclasses import dataclass

BUCKETS = 10_000


@dataclass(frozen=True)
class VariantSpec:
    key: str
    weight: int


def bucket(experiment_key: str, user_id: int) -> int:
    digest = hashlib.md5(f"{experiment_key}:{user_id}".encode()).digest()
    return int.from_bytes(digest[:4], "little") % BUCKETS


def bucket_sql(experiment_key_param: str, user_col: str = "user_id") -> str:
    return (
        f"reinterpretAsUInt32(substring(MD5(concat({{{experiment_key_param}:String}}, ':', "
        f"toString({user_col}))), 1, 4)) % {BUCKETS}"
    )


def assign(
    experiment_key: str, user_id: int, variants: list[VariantSpec], traffic_percent: int = 100
) -> str | None:
    """Return the variant key for a user, or None if the user is outside the
    experiment's traffic allocation. Traffic is the first `traffic_percent` of
    buckets; variants split that allocation proportionally to weight."""
    b = bucket(experiment_key, user_id)
    in_traffic = BUCKETS * traffic_percent // 100
    if b >= in_traffic:
        return None
    return variant_for_bucket(b, variants, in_traffic)


def variant_for_bucket(b: int, variants: list[VariantSpec], in_traffic: int) -> str:
    total = sum(v.weight for v in variants)
    edge = 0
    for v in variants:
        edge += in_traffic * v.weight // total
        if b < edge:
            return v.key
    return variants[-1].key


def variant_case_sql(experiment_key_param: str, variants: list[VariantSpec], traffic_percent: int) -> str:
    """multiIf expression mirroring `assign()`; NULL-free ('' = not in traffic)."""
    in_traffic = BUCKETS * traffic_percent // 100
    total = sum(v.weight for v in variants)
    b = bucket_sql(experiment_key_param)
    branches = []
    edge = 0
    for v in variants:
        edge += in_traffic * v.weight // total
        branches.append(f"{b} < {edge}, '{v.key}'")
    return f"multiIf({b} >= {in_traffic}, '', {', '.join(branches)}, '{variants[-1].key}')"
