"""Tests for GET /api/health."""

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["app"]
    assert body["version"]


def test_health_reports_service_configuration(client: TestClient) -> None:
    body = client.get("/api/health").json()

    services = body["services"]
    assert set(services) == {"gemini", "firecrawl", "elevenlabs"}
    assert all(isinstance(value, bool) for value in services.values())


def test_health_never_leaks_api_keys(client: TestClient) -> None:
    """The response must contain booleans only — no key material, ever."""
    raw = client.get("/api/health").text.lower()
    for forbidden in ("api_key", "sk-", "fc-", "aiza"):
        assert forbidden not in raw


def test_unknown_route_uses_shared_error_envelope(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404

    body = response.json()
    assert body["error"] == "http_error"
    assert "message" in body
