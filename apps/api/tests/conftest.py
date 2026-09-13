"""Shared fixtures. Integration fixtures skip cleanly when the databases are not reachable."""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session")
def api_client() -> Iterator:
    """Authenticated TestClient for the seeded demo project (PM role)."""
    try:
        from fastapi.testclient import TestClient

        from probelens.db.postgres import get_sessionmaker
        from probelens.main import app

        get_sessionmaker()().execute(__import__("sqlalchemy").text("select 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"databases not reachable: {exc}")
        return
    with TestClient(app) as client:
        res = client.post(
            "/api/auth/login", json={"email": "priya.pm@threadline.test", "password": "probelens"}
        )
        if res.status_code != 200:
            pytest.skip("demo users not seeded")
        yield client


@pytest.fixture(scope="session")
def analyst_client() -> Iterator:
    """Analyst role: can read ops objects but not write them."""
    try:
        from fastapi.testclient import TestClient

        from probelens.main import app
    except Exception as exc:  # pragma: no cover
        pytest.skip(str(exc))
        return
    with TestClient(app) as client:
        res = client.post(
            "/api/auth/login", json={"email": "arjun.analyst@threadline.test", "password": "probelens"}
        )
        if res.status_code != 200:
            pytest.skip("demo users not seeded")
        yield client
