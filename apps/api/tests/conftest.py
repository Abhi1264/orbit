"""Shared fixtures. Integration fixtures skip when databases are down (fail in CI)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.util import require_db


@pytest.fixture(scope="session")
def api_client() -> Iterator:
    try:
        from fastapi.testclient import TestClient
        from sqlalchemy import text

        from probelens.db.postgres import get_sessionmaker
        from probelens.main import app

        get_sessionmaker()().execute(text("select 1"))
    except Exception as exc:
        require_db(f"databases not reachable: {exc}")
        return
    with TestClient(app) as client:
        res = client.post(
            "/api/auth/login", json={"email": "priya.pm@threadline.test", "password": "probelens"}
        )
        if res.status_code != 200:
            require_db("demo users not seeded")
        yield client


@pytest.fixture(scope="session")
def analyst_client() -> Iterator:
    try:
        from fastapi.testclient import TestClient

        from probelens.main import app
    except Exception as exc:
        require_db(str(exc))
        return
    with TestClient(app) as client:
        res = client.post(
            "/api/auth/login", json={"email": "arjun.analyst@threadline.test", "password": "probelens"}
        )
        if res.status_code != 200:
            require_db("demo users not seeded")
        yield client
