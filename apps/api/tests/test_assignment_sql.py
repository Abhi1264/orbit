"""The ClickHouse bucketing expression must agree with the Python implementation,
otherwise retroactive analysis of app-created experiments would be silently wrong.
Needs a reachable ClickHouse; skipped otherwise."""

from probelens.experiments.assignment import VariantSpec, assign, bucket, bucket_sql, variant_case_sql
from tests.util import require_db


def _client():
    try:
        from probelens.db.clickhouse import get_readonly_client

        client = get_readonly_client()
        client.query("SELECT 1")
        return client
    except Exception as exc:
        require_db(f"ClickHouse not reachable: {exc}")
        raise


def test_sql_bucket_matches_python() -> None:
    client = _client()
    ids = list(range(1, 501))
    rows = client.query(
        f"SELECT user_id, {bucket_sql('k')} AS b FROM (SELECT arrayJoin({ids}) AS user_id) ORDER BY user_id",
        parameters={"k": "new_pdp_cta"},
    ).result_rows
    assert [b for _, b in rows] == [bucket("new_pdp_cta", uid) for uid in ids]


def test_sql_variant_matches_python() -> None:
    client = _client()
    variants = [VariantSpec("control", 40), VariantSpec("treatment", 60)]
    ids = list(range(1, 501))
    case = variant_case_sql("k", variants, traffic_percent=30)
    rows = client.query(
        f"SELECT user_id, {case} AS v FROM (SELECT arrayJoin({ids}) AS user_id) ORDER BY user_id",
        parameters={"k": "exp"},
    ).result_rows
    assert [v for _, v in rows] == [assign("exp", uid, variants, 30) or "" for uid in ids]
