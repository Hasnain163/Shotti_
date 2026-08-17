"""Shared service instances and FastAPI dependency providers.

The Gemini and Firecrawl clients are created once per process and reused, so HTTP
connections are not rebuilt on every request, and so the Firecrawl concurrency
semaphore is shared across requests rather than per-request (which would let
parallel requests blow through the provider's rate limit together).

Services are created lazily on first use and closed by the app's lifespan handler.
"""

import logging
from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings
from app.services.firecrawl import FirecrawlService
from app.services.gemini import GeminiService
from app.services.pipeline import VerificationPipeline

logger = logging.getLogger(__name__)

_gemini: GeminiService | None = None
_firecrawl: FirecrawlService | None = None


def get_gemini_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> GeminiService:
    global _gemini
    if _gemini is None:
        _gemini = GeminiService(settings)
    return _gemini


def get_firecrawl_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> FirecrawlService:
    global _firecrawl
    if _firecrawl is None:
        _firecrawl = FirecrawlService(settings)
    return _firecrawl


def get_pipeline(
    settings: Annotated[Settings, Depends(get_settings)],
    gemini: Annotated[GeminiService, Depends(get_gemini_service)],
    firecrawl: Annotated[FirecrawlService, Depends(get_firecrawl_service)],
) -> VerificationPipeline:
    return VerificationPipeline(settings=settings, gemini=gemini, firecrawl=firecrawl)


async def close_services() -> None:
    """Release upstream HTTP connections. Called on app shutdown."""
    global _gemini, _firecrawl
    for service in (_gemini, _firecrawl):
        if service is None:
            continue
        try:
            await service.aclose()
        except Exception:  # shutdown must not fail on cleanup
            logger.debug("service cleanup failed", exc_info=True)
    _gemini = None
    _firecrawl = None
