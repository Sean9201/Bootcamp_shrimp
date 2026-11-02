"""헬스체크·CORS·에러 형식."""


def test_health(client):
    r = client.get("/health")
    j = r.json()
    assert r.status_code == 200 and j["status"] == "ok"
    assert j["ai"] == {"classifier": False, "baselines": []} and j["llm"]["configured"] is False


def test_cors_frontend_origin(client):
    r = client.options("/health", headers={"Origin": "http://localhost:5500", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5500"


def test_unified_error_format(client):
    r = client.get("/api/v1/analyses/999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "analysis_not_found" and r.json()["error"]["message"]
    r = client.get("/api/v1/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "http_404"
