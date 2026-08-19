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


class TestDeploymentConfig:
    """Settings must load from environment variables alone.

    On a host there is no .env file — only real environment variables — and a
    dashboard can only supply plain strings.
    """

    def test_comma_separated_cors_origins_parse(self, monkeypatch) -> None:
        """This form crashed the app at startup before NoDecode was applied."""
        from app.config import Settings

        monkeypatch.setenv("CORS_ORIGINS", "https://a.netlify.app,https://b.netlify.app")
        settings = Settings(_env_file=None)

        assert settings.cors_origins == ["https://a.netlify.app", "https://b.netlify.app"]

    def test_json_array_cors_origins_parse(self, monkeypatch) -> None:
        from app.config import Settings

        monkeypatch.setenv("CORS_ORIGINS", '["https://a.app", "https://b.app"]')
        assert Settings(_env_file=None).cors_origins == ["https://a.app", "https://b.app"]

    def test_single_origin_parses(self, monkeypatch) -> None:
        from app.config import Settings

        monkeypatch.setenv("CORS_ORIGINS", "https://only.example.com")
        assert Settings(_env_file=None).cors_origins == ["https://only.example.com"]

    def test_keys_come_from_environment_without_an_env_file(self, monkeypatch) -> None:
        from app.config import Settings

        monkeypatch.setenv("GEMINI_API_KEY", "env-only-key")
        monkeypatch.setenv("FIRECRAWL_API_KEY", "env-only-key")
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

        settings = Settings(_env_file=None)

        assert settings.configured_services() == {
            "gemini": True,
            "firecrawl": True,
            "elevenlabs": False,
        }
