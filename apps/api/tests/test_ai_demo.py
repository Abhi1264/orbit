"""Deterministic analyst against the seeded dataset. Needs Postgres and ClickHouse; skipped otherwise.

These are the guarantees the UI and the acceptance run depend on: every fact cites a real tool
call, the seeded payment incident is attributed to UPI/PayU on Android with the 8.4.0 release,
and the same question always produces the same answer.
"""

from __future__ import annotations

from datetime import date

import pytest

from probelens.ai.demo import _anomaly_covers_scope, _merge_nearby_releases, _release_anchor, run_demo
from probelens.ai.schemas import AskContext
from probelens.ai.tools import ToolContext
from probelens.analytics.dimensions import Filter
from tests.util import require_db


def test_merge_nearby_releases_pins_payment_sdk() -> None:
    cands = [{"kind": "segment", "title": "Payment method: upi"}]
    releases = [
        {
            "id": 1,
            "version": "8.4.0",
            "platform": "android",
            "status": "completed",
            "name": "Android 8.4.0 — payment SDK upgrade",
            "affected_areas": ["checkout", "payments"],
        }
    ]
    android = Filter(dimension="platform", operator="eq", value="android")
    out = _merge_nearby_releases(cands, releases, "payment_success_rate", [android])
    assert any("8.4.0" in c["title"] for c in out)


def test_upi_anomaly_covers_android_question() -> None:
    android = [Filter(dimension="platform", operator="eq", value="android")]
    upi = {"scope": "Payment method = upi", "filters": [{"dimension": "payment_method", "value": "upi"}]}
    ios = {"scope": "Platform = ios", "filters": [{"dimension": "platform", "value": "ios"}]}
    assert _anomaly_covers_scope(upi, android)
    assert not _anomaly_covers_scope(ios, android)


def test_release_anchor_uses_payment_sdk_date() -> None:
    android = [Filter(dimension="platform", operator="eq", value="android")]
    hit = _release_anchor(
        [
            {
                "version": "8.4.0",
                "release_date": "2026-08-24",
                "platform": "android",
                "status": "completed",
                "affected_areas": ["payments"],
            }
        ],
        "payment_success_rate",
        android,
        date(2026, 9, 7),
    )
    assert hit and hit["version"] == "8.4.0"


@pytest.fixture(scope="module")
def tctx() -> ToolContext:
    try:
        from probelens.analytics.meta import _dimension_values, get_meta
        from probelens.db.postgres import get_sessionmaker

        meta = get_meta()
        if not meta.data_end:
            require_db("no data loaded")
        db = get_sessionmaker()()
        return ToolContext(db=db, today=meta.data_end, dimension_values=_dimension_values())
    except Exception as exc:
        require_db(f"databases not reachable: {exc}")
        raise


def _check_citations(answer, calls) -> None:
    ids = {c.id for c in calls}
    for f in answer.facts:
        assert f.source in ids, f
    for i in answer.inferences:
        assert i.basis and set(i.basis) <= ids, i


def test_payment_incident_is_attributed(tctx: ToolContext) -> None:
    answer, calls = run_demo("Why did payment success rate drop on android?", AskContext(), tctx)
    _check_citations(answer, calls)
    names = [c.name for c in calls]
    assert names[:4] == ["list_anomalies", "get_metric_summary", "root_cause", "breakdown_metric"]
    titles = " ".join(c.title.lower() for c in answer.candidates)
    assert "upi" in titles and "payu" in titles
    assert any("8.4.0" in c.title for c in answer.candidates)
    assert any(r.priority == "now" for r in answer.recommendations)
    assert any(link.href.startswith("/analytics?metric=payment_success_rate") for link in answer.links)
    # The monitor's window re-anchored the period.
    assert any("widened" in c for c in answer.caveats)


def test_answers_are_deterministic(tctx: ToolContext) -> None:
    a1, c1 = run_demo("Why did conversion fall last week?", AskContext(), tctx)
    a2, c2 = run_demo("Why did conversion fall last week?", AskContext(), tctx)
    assert a1.model_dump() == a2.model_dump()
    assert [(c.name, c.args) for c in c1] == [(c.name, c.args) for c in c2]


def test_what_question_uses_page_context(tctx: ToolContext) -> None:
    from probelens.analytics.dimensions import Filter

    ctx = AskContext(metric="conversion", filters=[Filter(dimension="platform", operator="eq", value="ios")])
    answer, calls = run_demo("how did it do last 7 days", ctx, tctx)
    _check_citations(answer, calls)
    assert calls[0].name == "get_metric_summary"
    assert calls[0].args["metric"] == "conversion"
    assert calls[0].args["filters"][0]["value"] == "ios"


def test_experiment_question_finds_the_experiment(tctx: ToolContext) -> None:
    answer, calls = run_demo("How is the new product page CTA experiment doing?", AskContext(), tctx)
    _check_citations(answer, calls)
    assert [c.name for c in calls] == ["list_experiments", "experiment_results"]
    assert calls[1].args["experiment"] == "new_pdp_cta"
    assert answer.links and answer.links[0].href.startswith("/experiments/")


def test_attention_clusters_shared_scope(tctx: ToolContext) -> None:
    answer, calls = run_demo("What needs attention right now?", AskContext(), tctx)
    _check_citations(answer, calls)
    assert calls[0].name == "list_anomalies"
    assert any("paid_social" in i.text for i in answer.inferences)


def test_unknown_metric_words_are_flagged_not_invented(tctx: ToolContext) -> None:
    answer, calls = run_demo("conversion for wholesale customers last week", AskContext(), tctx)
    assert any("wholesale" in c for c in answer.caveats)
    assert calls[0].args.get("filters", []) == []
