"""Tests for the result cache and its use by the pipeline."""

import time
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies import get_result_cache
from app.main import app
from app.models.verify import VerifyResponse
from app.services.cache import TTLCache
from app.services.pipeline import VerificationPipeline, make_claim_id
from tests.test_verify import (
    install,
    make_bundle,
    make_claim_analysis,
    make_evidence_analysis,
)


class TestTTLCache:
    def test_stores_and_returns(self) -> None:
        cache: TTLCache[str] = TTLCache(ttl_seconds=60, max_entries=4)
        cache.set("a", "value")
        assert cache.get("a") == "value"

    def test_missing_key_is_none(self) -> None:
        cache: TTLCache[str] = TTLCache(ttl_seconds=60, max_entries=4)
        assert cache.get("nope") is None

    def test_entry_expires(self) -> None:
        cache: TTLCache[str] = TTLCache(ttl_seconds=0.05, max_entries=4)
        cache.set("a", "value")
        time.sleep(0.08)
        assert cache.get("a") is None

    def test_evicts_least_recently_used(self) -> None:
        cache: TTLCache[str] = TTLCache(ttl_seconds=60, max_entries=2)
        cache.set("a", "1")
        cache.set("b", "2")
        cache.get("a")  # 'a' becomes most recent, so 'b' is next out
        cache.set("c", "3")

        assert cache.get("a") == "1"
        assert cache.get("b") is None
        assert cache.get("c") == "3"
        assert len(cache) == 2


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def install_with_cache() -> TTLCache[VerifyResponse]:
    install(
        claim_result=make_claim_analysis(),
        research_result=make_bundle(),
        evidence_result=make_evidence_analysis(),
    )
    cache: TTLCache[VerifyResponse] = TTLCache(ttl_seconds=60, max_entries=8)
    app.dependency_overrides[get_result_cache] = lambda: cache
    return cache


def test_repeat_claim_is_served_from_cache(client: TestClient) -> None:
    """The reason this exists: a repeated demo claim must not re-spend API quota."""
    cache = install_with_cache()
    payload = {"claim": "Bangladesh won the ICC Champions Trophy in 2017."}

    first = client.post("/api/verify", json=payload).json()
    assert first["meta"]["cached"] is False
    assert len(cache) == 1

    second = client.post("/api/verify", json=payload).json()
    assert second["meta"]["cached"] is True
    assert second["verdict"] == first["verdict"]
    assert second["sources"] == first["sources"]


def test_cache_hit_calls_no_upstream_service(client: TestClient) -> None:
    install_with_cache()
    payload = {"claim": "A repeated claim for the cache."}

    client.post("/api/verify", json=payload)

    # Re-install fresh mocks that would fail loudly if used.
    gemini, firecrawl = install(
        claim_result=AssertionError("claim analysis must not run on a cache hit"),
    )
    firecrawl.research = AsyncMock(
        side_effect=AssertionError("research must not run on a cache hit")
    )
    cache_holder = app.dependency_overrides.get(get_result_cache)
    assert cache_holder is not None  # preserved by install()

    body = client.post("/api/verify", json=payload).json()

    assert body["meta"]["cached"] is True
    gemini.analyze_claim.assert_not_awaited()
    firecrawl.research.assert_not_awaited()


def test_whitespace_and_case_variants_share_a_cache_entry(client: TestClient) -> None:
    cache = install_with_cache()
    client.post("/api/verify", json={"claim": "Water boils at 100C."})
    client.post("/api/verify", json={"claim": "  water boils at 100C.  "})

    assert len(cache) == 1


def test_cached_flag_keeps_reported_timing_honest(client: TestClient) -> None:
    """A cached response must not present the original duration as fresh work."""
    install_with_cache()
    payload = {"claim": "A claim to check twice."}

    client.post("/api/verify", json=payload)
    second = client.post("/api/verify", json=payload).json()

    assert second["meta"]["cached"] is True
    assert second["meta"]["duration_ms"] >= 0


def test_cache_can_be_disabled_by_zero_ttl() -> None:
    settings = Settings(cache_ttl_seconds=0, gemini_api_key=None, firecrawl_api_key=None)
    assert get_result_cache(settings) is None


@pytest.mark.asyncio
async def test_pipeline_without_a_cache_still_works() -> None:
    """The cache is optional; passing None must not break verification."""
    from app.models.verify import VerifyRequest

    settings = Settings(gemini_api_key="k", firecrawl_api_key="k")
    gemini = type(
        "G",
        (),
        {
            "analyze_claim": AsyncMock(return_value=make_claim_analysis()),
            "analyze_evidence": AsyncMock(return_value=make_evidence_analysis()),
        },
    )()
    firecrawl = type("F", (), {"research": AsyncMock(return_value=make_bundle())})()

    pipeline = VerificationPipeline(settings, gemini, firecrawl, cache=None)
    response = await pipeline.verify(VerifyRequest(claim="A claim without a cache."))

    assert response.meta.cached is False
    assert response.claim_id == make_claim_id("A claim without a cache.")
