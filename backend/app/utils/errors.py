"""Shared error types and the JSON error envelope used by every endpoint."""

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Uniform error body so the frontend can render failures without guessing."""

    error: str = Field(description="Machine-readable error code, e.g. 'service_error'.")
    message: str = Field(description="Human-readable message, safe to display.")
    details: dict[str, Any] | None = Field(
        default=None, description="Optional extra context (validation errors, etc.)."
    )


class ShottiError(Exception):
    """Base class for expected, handled application errors."""

    status_code = 500
    error_code = "internal_error"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ServiceError(ShottiError):
    """An upstream API (Gemini, Firecrawl, ElevenLabs) failed or timed out."""

    status_code = 502
    error_code = "service_error"


class RateLimitError(ShottiError):
    """An upstream API rejected us for rate limiting or quota (HTTP 429).

    Kept separate from ServiceError because the user-facing advice is different:
    wait and retry, rather than check the configuration.
    """

    status_code = 429
    error_code = "rate_limited"


class ServiceUnavailableError(ShottiError):
    """A required integration is not configured (missing API key)."""

    status_code = 503
    error_code = "service_unavailable"


class UnsupportedMediaTypeError(ShottiError):
    """The upload is not an image format we can read."""

    status_code = 415
    error_code = "unsupported_media_type"


class PayloadTooLargeError(ShottiError):
    """The upload exceeds the configured size limit."""

    status_code = 413
    error_code = "payload_too_large"


class InvalidClaimError(ShottiError):
    """The submitted claim cannot be fact-checked (empty, opinion, gibberish)."""

    status_code = 422
    error_code = "invalid_claim"
