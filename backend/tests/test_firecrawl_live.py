"""Opt-in live test against the real Firecrawl API.

    ./.venv/Scripts/python.exe -m pytest -m live

Kept out of the default run so `pytest` stays offline and spends no credits.
"""

import pytest

from app.config import get_settings
from app.models.source import SourceType
from app.services.firecrawl import FirecrawlService

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not get_settings().firecrawl_api_key,
        reason="FIRECRAWL_API_KEY not configured",
    ),
]


@pytest.mark.asyncio
async def test_live_research_returns_normalised_sources() -> None:
    service = FirecrawlService(get_settings())
    try:
        bundle = await service.research(
            ["Bangladesh Champions Trophy 2017 winner", "চ্যাম্পিয়ন্স ট্রফি ২০১৭ বিজয়ী"],
            max_sources=3,
        )
    finally:
        await service.aclose()

    assert bundle.has_evidence, "expected at least one reachable source"
    for source in bundle.sources:
        assert source.url.startswith("http")
        assert source.domain and " " not in source.domain
        assert source.title
        assert source.content
        assert isinstance(source.source_type, SourceType)
        assert len(source.content) <= get_settings().firecrawl_max_chars_per_source + 1

    urls = [source.url for source in bundle.sources]
    assert len(urls) == len(set(urls)), "duplicate URLs must be collapsed"
    assert bundle.total_content_chars <= get_settings().firecrawl_max_total_chars


@pytest.mark.asyncio
async def test_live_nonsense_query_degrades_without_raising() -> None:
    """No results is a valid outcome, not an error."""
    service = FirecrawlService(get_settings())
    try:
        bundle = await service.research(
            ["zxqwv nonexistent claim about qqzzxx 99812 flurble"], max_sources=2
        )
    finally:
        await service.aclose()

    assert isinstance(bundle.sources, list)
