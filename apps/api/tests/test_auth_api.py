"""Authentication, RBAC and user administration."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from probelens.core.permissions import ROLE_PERMISSIONS, Permission, has_permission
from probelens.models.enums import Role

pytestmark = pytest.mark.usefixtures("api_client")


def test_permission_matrix_is_monotonic() -> None:
    viewer, analyst, pm, admin = (
        ROLE_PERMISSIONS[r] for r in (Role.viewer, Role.analyst, Role.pm, Role.admin)
    )
    assert viewer < analyst < pm < admin
    assert admin == frozenset(Permission)
    assert not has_permission(Role.viewer, Permission.use_analyst)
    assert not has_permission(Role.analyst, Permission.manage_releases)
    assert not has_permission(Role.pm, Permission.manage_users)


def test_me_reports_role_permissions(api_client: TestClient) -> None:
    me = api_client.get("/api/auth/me").json()
    assert me["role"] == "pm"
    assert set(me["permissions"]) == {p.value for p in ROLE_PERMISSIONS[Role.pm]}
    roles = {r["role"]: r["permissions"] for r in api_client.get("/api/auth/roles").json()}
    assert roles["viewer"] == sorted(p.value for p in ROLE_PERMISSIONS[Role.viewer])


def test_unauthenticated_and_bad_password(api_client: TestClient) -> None:
    anon = TestClient(api_client.app)
    assert anon.get("/api/auth/me").status_code == 401
    assert anon.get("/api/releases").status_code == 401
    bad = anon.post("/api/auth/login", json={"email": "priya.pm@threadline.test", "password": "wrong"})
    assert bad.status_code == 401


def test_login_is_rate_limited() -> None:
    from probelens.core import ratelimit

    key = "test:ratelimit"
    ratelimit.reset(key)
    results = [ratelimit.hit(key, 3, 60)[0] for _ in range(5)]
    assert results == [True, True, True, False, False]
    ratelimit.reset(key)
    assert ratelimit.hit(key, 3, 60)[0] is True
    ratelimit.reset(key)


def test_security_headers_and_request_id(api_client: TestClient) -> None:
    res = api_client.get("/api/auth/me", headers={"X-Request-ID": "abc123"})
    assert res.headers["X-Request-ID"] == "abc123"
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["Cache-Control"] == "no-store"


def test_pm_cannot_administer_users(api_client: TestClient) -> None:
    assert api_client.get("/api/auth/admin/users").status_code == 403


def test_admin_user_lifecycle(api_client: TestClient) -> None:
    admin = TestClient(api_client.app)
    res = admin.post("/api/auth/login", json={"email": "admin@threadline.test", "password": "probelens"})
    assert res.status_code == 200
    me = res.json()

    created = admin.post(
        "/api/auth/admin/users",
        json={
            "email": "Test.User@threadline.test",
            "name": "Test User",
            "password": "password123",
            "role": "viewer",
        },
    )
    assert created.status_code == 201, created.text
    user = created.json()
    assert user["email"] == "test.user@threadline.test"
    try:
        dup = admin.post(
            "/api/auth/admin/users",
            json={"email": "test.user@threadline.test", "name": "Dup", "password": "password123"},
        )
        assert dup.status_code == 400

        # The new viewer can sign in and is denied writes.
        viewer = TestClient(api_client.app)
        assert (
            viewer.post(
                "/api/auth/login", json={"email": user["email"], "password": "password123"}
            ).status_code
            == 200
        )
        assert viewer.get("/api/releases").status_code == 200
        assert viewer.post("/api/ai/ask", json={"question": "why?", "context": {}}).status_code == 403
        assert viewer.post("/api/comments/release/1", json={"body": "hi"}).status_code == 403

        # Password change requires the current password.
        assert (
            viewer.post(
                "/api/auth/password", json={"current_password": "nope", "new_password": "password456"}
            ).status_code
            == 400
        )
        assert (
            viewer.post(
                "/api/auth/password", json={"current_password": "password123", "new_password": "password456"}
            ).status_code
            == 204
        )

        # Promote, then deactivate; a deactivated user's session stops working.
        promoted = admin.patch(f"/api/auth/admin/users/{user['id']}", json={"role": "analyst"}).json()
        assert promoted["role"] == "analyst"
        assert viewer.get("/api/auth/me").json()["role"] == "analyst"
        admin.patch(f"/api/auth/admin/users/{user['id']}", json={"is_active": False})
        assert viewer.get("/api/auth/me").status_code == 401
        assert user["id"] not in {u["id"] for u in admin.get("/api/auth/users").json()}

        # Self-protection rules.
        assert admin.patch(f"/api/auth/admin/users/{me['id']}", json={"is_active": False}).status_code == 403
        assert admin.patch(f"/api/auth/admin/users/{me['id']}", json={"role": "pm"}).status_code == 403
        # Users who own records cannot be hard-deleted; the seeded PM owns investigations.
        pm_id = api_client.get("/api/auth/me").json()["id"]
        assert admin.delete(f"/api/auth/admin/users/{pm_id}").status_code == 409
        assert admin.delete(f"/api/auth/admin/users/{me['id']}").status_code == 403
    finally:
        assert admin.delete(f"/api/auth/admin/users/{user['id']}").status_code == 204
