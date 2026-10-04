import time
from typing import Any

import httpx


class MetabaseError(RuntimeError):
    pass


class Metabase:
    def __init__(self, url: str, timeout: float = 30.0) -> None:
        self._http = httpx.Client(base_url=url.rstrip("/"), timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = self._http.request(method, f"/api{path}", **kwargs)
        if resp.status_code >= 400:
            raise MetabaseError(f"{method} /api{path} -> {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else None

    def get(self, path: str, **params: Any) -> Any:
        return self.request("GET", path, params=params or None)

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return self.request("POST", path, json=body or {})

    def put(self, path: str, body: dict[str, Any]) -> Any:
        return self.request("PUT", path, json=body)

    def wait_healthy(self, seconds: float = 300) -> None:
        deadline = time.monotonic() + seconds
        while True:
            try:
                if self._http.get("/api/health").json().get("status") == "ok":
                    return
            except (httpx.HTTPError, ValueError):
                pass
            if time.monotonic() > deadline:
                raise MetabaseError(f"Metabase did not become healthy within {seconds:g}s")
            time.sleep(3)

    def login(self, email: str, password: str, site_name: str) -> bool:
        props = self.get("/session/properties")
        first_run = not props.get("has-user-setup")
        if first_run:
            session = self.post(
                "/setup",
                {
                    "token": props["setup-token"],
                    "user": {
                        "email": email,
                        "password": password,
                        "first_name": "Orbit",
                        "last_name": "Admin",
                        "site_name": site_name,
                    },
                    "prefs": {"site_name": site_name, "site_locale": "en", "allow_tracking": False},
                },
            )
        else:
            session = self.post("/session", {"username": email, "password": password})
        self._http.headers["X-Metabase-Session"] = session["id"]
        return first_run

    def databases(self) -> list[dict[str, Any]]:
        result = self.get("/database")
        return result["data"] if isinstance(result, dict) else result

    def tables(self, database_id: int) -> dict[str, dict[str, Any]]:
        tables: dict[str, dict[str, Any]] = {}
        for table in self.get(f"/database/{database_id}/metadata")["tables"]:
            tables[table["name"]] = table
            if table.get("schema"):
                tables[f"{table['schema']}.{table['name']}"] = table
        return tables
