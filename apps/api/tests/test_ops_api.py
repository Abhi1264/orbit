"""Releases, SOPs/checklists, knowledge, feedback, decisions and search over the seeded data.

Each test cleans up what it creates so the demo dataset is unchanged afterwards.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("api_client")


def _android(api_client) -> dict:
    rels = api_client.get("/api/releases", params={"platform": "android"}).json()
    return next(r for r in rels if r["version"] == "8.4.0")


# --------------------------------------------------------------------------- releases


def test_release_detail_has_checklist_timeline_and_impact(api_client) -> None:
    rel = _android(api_client)
    detail = api_client.get(f"/api/releases/{rel['id']}").json()
    assert detail["checklist_progress"]["total"] == 9
    kinds = {e["kind"] for e in detail["timeline"]}
    assert {"status_change", "rollout"} <= kinds
    assert detail["checklists"][0]["done_count"] == 7

    impact = api_client.get(f"/api/releases/{rel['id']}/impact").json()
    assert impact["scope"] == ["platform = android"]
    by_key = {m["metric_key"]: m for m in impact["metrics"]}
    # The seeded incident: UPI collect-request timeouts after 8.4.0.
    assert by_key["payment_success_rate"]["tone"] == "bad"
    assert by_key["payment_success_rate"]["rel_change"] < -0.03
    # affected_areas=payments adds the failure-rate read.
    assert "payment_failure_rate" in by_key
    assert by_key["payment_failure_rate"]["tone"] == "bad"


def test_release_lifecycle_writes_timeline(api_client) -> None:
    sops = api_client.get("/api/ops/sops").json()
    launch = next(s for s in sops if s["category"] == "release")
    created = api_client.post(
        "/api/releases",
        json={
            "version": "test-9.9.9",
            "name": "Test release lifecycle",
            "platform": "web",
            "release_date": "2026-09-20",
            "affected_areas": ["search"],
            "sop_id": launch["id"],
        },
    )
    assert created.status_code == 201, created.text
    rel = created.json()
    rid = rel["id"]
    try:
        assert rel["status"] == "planned"
        assert len(rel["checklists"]) == 1
        assert rel["checklists"][0]["total_count"] == len(launch["items"])

        # Duplicate version+platform is rejected.
        dup = api_client.post(
            "/api/releases",
            json={"version": "test-9.9.9", "name": "Dup", "platform": "web", "release_date": "2026-09-21"},
        )
        assert dup.status_code == 400

        # Rolling out: rollout note lands in the timeline and status auto-advances.
        upd = api_client.patch(f"/api/releases/{rid}", json={"rollout_percent": 25, "note": "Canary"}).json()
        assert upd["status"] == "rolling_out"
        assert any(e["kind"] == "rollout" and "Canary" in e["note"] for e in upd["timeline"])

        # Completing sets rollout to 100.
        upd = api_client.patch(f"/api/releases/{rid}", json={"status": "completed"}).json()
        assert upd["rollout_percent"] == 100

        # Shipped releases cannot be deleted.
        assert api_client.delete(f"/api/releases/{rid}").status_code == 400

        # Checklist item toggling drives checklist status.
        cid = rel["checklists"][0]["id"]
        key = rel["checklists"][0]["items"][0]["key"]
        toggled = api_client.patch(f"/api/ops/checklists/{cid}/items/{key}", json={"done": True}).json()
        assert toggled["status"] == "in_progress" and toggled["done_count"] == 1
        assert toggled["items"][0]["done_at"] is not None
    finally:
        api_client.patch(f"/api/releases/{rid}", json={"status": "planned", "rollout_percent": 0})
        assert api_client.delete(f"/api/releases/{rid}").status_code == 204


def test_release_writes_need_permission(analyst_client) -> None:
    res = analyst_client.post(
        "/api/releases",
        json={"version": "x", "name": "Nope please", "platform": "web", "release_date": "2026-09-20"},
    )
    assert res.status_code == 403


# --------------------------------------------------------------------------- ops


def test_sop_crud_and_standalone_checklist(api_client) -> None:
    created = api_client.post(
        "/api/ops/sops",
        json={
            "title": "Test SOP",
            "category": "test",
            "items": [{"key": "a", "label": "Step A", "owner_role": "pm"}, {"key": "b", "label": "Step B"}],
        },
    )
    assert created.status_code == 201, created.text
    sop = created.json()
    dup_keys = api_client.post(
        "/api/ops/sops",
        json={
            "title": "Bad SOP",
            "category": "test",
            "items": [{"key": "a", "label": "1"}, {"key": "a", "label": "2"}],
        },
    )
    assert dup_keys.status_code == 400

    cl = api_client.post("/api/ops/checklists", json={"sop_id": sop["id"], "title": "Standalone"}).json()
    assert cl["release_id"] is None and cl["total_count"] == 2
    for key in ("a", "b"):
        cl = api_client.patch(f"/api/ops/checklists/{cl['id']}/items/{key}", json={"done": True}).json()
    assert cl["status"] == "complete"
    assert api_client.get(f"/api/ops/sops/{sop['id']}").json()["run_count"] == 1
    assert api_client.delete(f"/api/ops/sops/{sop['id']}").status_code == 204
    # The checklist survives without its SOP back-reference.
    survivor = api_client.get("/api/ops/checklists").json()[0]
    assert survivor["id"] == cl["id"] and survivor["sop_id"] is None
    assert api_client.get(f"/api/ops/sops/{sop['id']}").status_code == 404
    assert api_client.delete(f"/api/ops/checklists/{cl['id']}").status_code == 204


def test_knowledge_search_and_edit(api_client) -> None:
    docs = api_client.get("/api/ops/knowledge", params={"q": "collect request timeout"}).json()
    assert docs and docs[0]["title"] == "Payments stack overview"
    assert "…" in docs[0]["excerpt"] or len(docs[0]["excerpt"]) <= 180

    created = api_client.post(
        "/api/ops/knowledge",
        json={"title": "Test doc", "body": "## Heading\nBody text.", "tags": ["Test", " x "]},
    ).json()
    try:
        assert created["tags"] == ["test", "x"]
        tagged = api_client.get("/api/ops/knowledge", params={"tag": "test"}).json()
        assert any(d["id"] == created["id"] for d in tagged)
        updated = api_client.patch(f"/api/ops/knowledge/{created['id']}", json={"title": "Test doc 2"}).json()
        assert updated["title"] == "Test doc 2"
    finally:
        assert api_client.delete(f"/api/ops/knowledge/{created['id']}").status_code == 204


def test_feedback_themes_and_linking(api_client) -> None:
    themes = api_client.get("/api/ops/feedback/themes").json()
    payments = next(t for t in themes if t["theme"] == "payments")
    assert payments["total"] >= 4 and payments["negative"] >= 3

    android = _android(api_client)
    linked = api_client.get(
        "/api/ops/feedback", params={"linked_type": "release", "linked_id": android["id"]}
    ).json()
    assert len(linked) >= 3 and all(f["linked"]["type"] == "release" for f in linked)

    bad = api_client.post(
        "/api/ops/feedback",
        json={
            "source": "support",
            "theme": "test",
            "body": "xyz",
            "linked_entity_type": "release",
            "linked_entity_id": 0,
        },
    )
    assert bad.status_code == 404

    created = api_client.post(
        "/api/ops/feedback",
        json={
            "source": "survey",
            "theme": "Test Theme",
            "body": "Test feedback body",
            "sentiment": "negative",
        },
    ).json()
    assert created["theme"] == "test_theme" and created["status"] == "new"
    upd = api_client.patch(
        f"/api/ops/feedback/{created['id']}",
        json={"status": "triaged", "linked_entity_type": "release", "linked_entity_id": android["id"]},
    ).json()
    assert upd["linked"]["id"] == android["id"] and upd["status"] == "triaged"
    upd = api_client.patch(
        f"/api/ops/feedback/{created['id']}", json={"unlink": True, "status": "dismissed"}
    ).json()
    assert upd["linked"] is None and upd["status"] == "dismissed"


def test_ops_writes_need_permission(analyst_client) -> None:
    assert analyst_client.get("/api/ops/feedback").status_code == 200
    res = analyst_client.post("/api/ops/feedback", json={"source": "support", "theme": "test", "body": "xyz"})
    assert res.status_code == 403


# --------------------------------------------------------------------------- decisions


def test_decisions_link_and_follow_up(api_client) -> None:
    rows = api_client.get("/api/decisions").json()
    ship = next(d for d in rows if d["title"].startswith("Ship free shipping"))
    assert ship["linked"][0]["type"] == "experiment"
    detail = api_client.get(f"/api/decisions/{ship['id']}").json()
    assert detail["evidence"] and detail["expected_impact"]

    created = api_client.post(
        "/api/decisions",
        json={
            "title": "Test decision",
            "decision": "Do the thing",
            "follow_up_date": "2000-01-01",
            "experiment_id": ship["linked"][0]["id"],
        },
    ).json()
    try:
        assert created["follow_up_due"] is True
        due = api_client.get("/api/decisions", params={"due_only": True}).json()
        assert any(d["id"] == created["id"] for d in due)
        superseded = api_client.patch(f"/api/decisions/{created['id']}", json={"status": "superseded"}).json()
        assert superseded["follow_up_due"] is False
        missing = api_client.post(
            "/api/decisions", json={"title": "Bad", "decision": "nothing", "release_id": 0}
        )
        assert missing.status_code == 404
    finally:
        assert api_client.delete(f"/api/decisions/{created['id']}").status_code == 204


# --------------------------------------------------------------------------- search


def test_global_search_groups_and_fallbacks(api_client) -> None:
    res = api_client.get("/api/search", params={"q": "payment failure"}).json()
    assert res["total"] > 0
    assert "release" in res["groups"] and "metric" in res["groups"]
    assert any(h["extra"]["key"] == "payment_failure_rate" for h in res["groups"]["metric"])
    assert all(
        not w.startswith("#") for h in res["groups"].get("knowledge", []) for w in h["subtitle"].split()
    )

    # Partial version number falls back to substring matching.
    res = api_client.get("/api/search", params={"q": "8.4", "types": "release"}).json()
    assert set(res["groups"]) == {"release"}
    assert {h["extra"]["version"] for h in res["groups"]["release"]} >= {"8.4.0", "8.4.1"}

    assert api_client.get("/api/search", params={"q": "x"}).status_code == 422
