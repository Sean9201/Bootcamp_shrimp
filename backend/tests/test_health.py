"""헬스체크·CORS 기본 동작."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_health():
    r = TestClient(create_app()).get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_cors_frontend_origin():
    r = TestClient(create_app()).options(
        "/health", headers={"Origin": "http://localhost:5500", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5500"
