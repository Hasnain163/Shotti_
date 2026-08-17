"""Opt-in live test against the real Gemini API.

Skipped unless a real key is configured AND live tests are requested:

    ./.venv/Scripts/python.exe -m pytest -m live

Kept separate from the mocked suite so `pytest` stays offline, fast, and green
without any credentials.
"""

import pytest

from app.config import get_settings
from app.models.claim import ClaimAnalysis
from app.services.gemini import GeminiService

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not get_settings().gemini_api_key,
        reason="GEMINI_API_KEY not configured",
    ),
]


@pytest.mark.asyncio
async def test_live_analyze_bangla_claim() -> None:
    service = GeminiService(get_settings())
    result = await service.analyze_claim("গতকাল ঢাকায় ভূমিকম্প হয়েছে।")

    assert isinstance(result, ClaimAnalysis)
    assert result.language.value in {"bn", "mixed"}
    assert result.search_queries, "the research stage needs at least one query"
    assert result.verification_questions
    assert result.resolved_timeframe, "'গতকাল' should resolve to an absolute date"
    # No printing: Bangla output crashes a cp1252 Windows console. Use
    # scripts/analyze_claim.py to eyeball real results.
    assert result.is_checkable is True


@pytest.mark.asyncio
async def test_live_rejects_opinion_as_uncheckable() -> None:
    service = GeminiService(get_settings())
    result = await service.analyze_claim("Biryani is the most delicious food in the world.")

    assert result.is_checkable is False
    assert result.uncheckable_reason
