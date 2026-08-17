"""Opt-in live test of the evidence analysis agent.

    ./.venv/Scripts/python.exe -m pytest -m live

Uses a claim with a well-documented answer, and asserts on the properties that must
hold for any correct analysis rather than on exact wording, which varies per run.
"""

import pytest

from app.config import get_settings
from app.models.verify import Verdict
from app.services.firecrawl import FirecrawlService
from app.services.gemini import GeminiService
from app.utils.text import quote_is_grounded

settings = get_settings()

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not (settings.gemini_api_key and settings.firecrawl_api_key),
        reason="both GEMINI_API_KEY and FIRECRAWL_API_KEY are required",
    ),
]


@pytest.mark.asyncio
async def test_live_false_claim_is_not_reported_as_true() -> None:
    """Bangladesh did not win the 2017 Champions Trophy; Pakistan did."""
    gemini = GeminiService(settings)
    firecrawl = FirecrawlService(settings)

    try:
        claim_analysis = await gemini.analyze_claim(
            "Bangladesh won the ICC Champions Trophy in 2017."
        )
        bundle = await firecrawl.research(claim_analysis.search_queries, max_sources=4)
        result = await gemini.analyze_evidence(claim_analysis, bundle.sources)
    finally:
        await gemini.aclose()
        await firecrawl.aclose()

    assert result.verdict is not Verdict.LIKELY_TRUE
    assert result.verdict in {Verdict.LIKELY_FALSE, Verdict.MISLEADING, Verdict.UNVERIFIED}
    assert result.short_explanation

    # Every surviving quote must really be in the source it cites.
    for item in result.supporting_evidence + result.contradicting_evidence:
        assert 0 <= item.source_index < len(bundle.sources)
        source = bundle.sources[item.source_index]
        assert quote_is_grounded(item.quote, source.content), (
            f"ungrounded quote survived validation: {item.quote[:80]!r}"
        )

    # Assessments may only reference retrieved sources.
    retrieved_urls = {source.url for source in bundle.sources}
    for assessment in result.source_assessments:
        assert assessment.url in retrieved_urls
