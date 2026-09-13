def test_system_status_reports_a_live_stack(api_client) -> None:
    res = api_client.get("/api/system/status")
    assert res.status_code == 200
    body = res.json()
    assert {d["name"]: d["ok"] for d in body["dependencies"]} == {
        "postgres": True,
        "clickhouse": True,
        "redis": True,
    }
    assert body["data"]["events"] > 0
    assert body["worker_alive"]
    by_job = {j["job"]: j for j in body["jobs"]}
    assert by_job["detect_anomalies"]["ok"] is True
