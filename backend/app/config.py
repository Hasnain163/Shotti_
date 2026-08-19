"""Application configuration, loaded from environment variables."""

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# The repo-root `.env` lives two levels above this file (backend/app/config.py).
_ENV_FILE = "../.env"


class Settings(BaseSettings):
    """Env-backed settings. Keys are optional here so the app can boot and serve
    /api/health without them; each service validates its own key when first used."""

    model_config = SettingsConfigDict(
        env_file=(_ENV_FILE, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Shotti? AI"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    gemini_api_key: str | None = None
    # gemini-2.5-* is closed to new API keys, so do not "downgrade" this default.
    # Verified working and fastest of the current flash tier (~4.6s per analysis).
    gemini_model: str = "gemini-3.7-flash"
    # Milliseconds, matching the SDK's HttpOptions.timeout unit.
    gemini_timeout_ms: int = 30_000
    # Flash models return transient 503s under load; retry those, never 4xx.
    gemini_max_retries: int = 2
    gemini_retry_backoff_seconds: float = 1.0

    firecrawl_api_key: str | None = None
    # Results requested per query, before de-duplication and ranking.
    firecrawl_search_limit: int = 5
    # Pages actually scraped per claim. The main cost/latency dial.
    firecrawl_max_sources: int = 6
    # Viewpoint diversity: eight pages from one outlet is still one viewpoint.
    firecrawl_max_per_domain: int = 2
    firecrawl_max_chars_per_source: int = 3_000
    # Bounds the whole analysis prompt; per-source caps alone do not.
    firecrawl_max_total_chars: int = 15_000
    firecrawl_search_timeout_ms: int = 20_000
    firecrawl_scrape_timeout_ms: int = 15_000
    # The free plan allows ~10 requests/minute. One claim fires several searches and
    # up to max_sources scrapes, so an unthrottled burst rate-limits itself.
    firecrawl_max_concurrent_requests: int = 3

    # Whole-pipeline ceiling, so a slow stage cannot hang the HTTP request forever.
    pipeline_timeout_seconds: float = 90.0

    # Screenshot uploads. 5 MB comfortably covers a phone screenshot.
    screenshot_max_bytes: int = 5 * 1024 * 1024

    # Repeat verifications of the same claim are served from memory rather than
    # re-spending API quota. Set the TTL to 0 to disable.
    cache_ttl_seconds: float = 900.0
    cache_max_entries: int = 128

    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str | None = None

    # NoDecode is essential, not cosmetic: without it pydantic-settings tries to
    # JSON-decode any list-typed environment variable before validators run, so a
    # normal "https://a.app,https://b.app" value raises SettingsError and the app
    # never starts. NoDecode hands the raw string to the validator below instead.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a comma-separated string, a JSON array, or a list.

        Hosting dashboards only take plain strings, so comma-separated is the form
        that actually gets typed in practice.
        """
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                import json

                try:
                    return json.loads(text)
                except ValueError:
                    pass
            return [origin.strip() for origin in text.split(",") if origin.strip()]
        return value

    def configured_services(self) -> dict[str, bool]:
        """Which integrations have credentials. Booleans only — never expose keys."""
        return {
            "gemini": bool(self.gemini_api_key),
            "firecrawl": bool(self.firecrawl_api_key),
            "elevenlabs": bool(self.elevenlabs_api_key),
        }


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor, suitable for use as a FastAPI dependency."""
    return Settings()
