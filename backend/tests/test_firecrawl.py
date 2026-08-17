"""Tests for the Firecrawl research agent.

Fully mocked: no network, no FIRECRAWL_API_KEY required. Search and scrape are
patched at the SDK method boundary, so the service's own normalisation, de-duplication,
ranking, budgeting, and failure handling are all exercised for real.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from firecrawl.v2.utils.error_handler import (
    BadRequestError,
    FirecrawlError,
    PaymentRequiredError,
    RateLimitError as FirecrawlRateLimitError,
    UnauthorizedError,
)

from app.config import Settings
from app.models.source import SourceType
from app.services.firecrawl import MIN_USEFUL_CONTENT_CHARS, FirecrawlService
from app.utils.errors import RateLimitError, ServiceError, ServiceUnavailableError

# AsyncFirecrawl is a facade that binds these methods off an inner client at
# construction time, so the inner class is the only patchable seam.
SEARCH_TARGET = "firecrawl.v2.client_async.AsyncFirecrawlClient.search"
SCRAPE_TARGET = "firecrawl.v2.client_async.AsyncFirecrawlClient.scrape"

ARTICLE = (
    "An earthquake of magnitude 5.2 was recorded near Dhaka early on Saturday. "
    "The Bangladesh Meteorological Department confirmed the tremor was felt across "
    "several districts, with no immediate reports of casualties or structural damage. "
    "Residents described shaking that lasted several seconds before subsiding. "
)


def make_settings(**overrides) -> Settings:
    """Deterministic settings that ignore the developer's real .env."""
    defaults = {
        "firecrawl_api_key": "test-key-not-real",
        "gemini_api_key": None,
        "elevenlabs_api_key": None,
        "firecrawl_search_limit": 5,
        "firecrawl_max_sources": 6,
        "firecrawl_max_per_domain": 2,
        "firecrawl_max_chars_per_source": 3_000,
        "firecrawl_max_total_chars": 15_000,
    }
    return Settings(**{**defaults, **overrides})


def web_hit(url: str, title: str = "Report", description: str = "A summary.") -> SimpleNamespace:
    return SimpleNamespace(url=url, title=title, description=description, position=1)


def news_hit(url: str, title: str = "News", date: str | None = "2026-08-16") -> SimpleNamespace:
    return SimpleNamespace(url=url, title=title, snippet="A news summary.", date=date)


def search_data(web=None, news=None) -> SimpleNamespace:
    return SimpleNamespace(web=web or [], news=news or [], images=[], developer=[])


def document(markdown: str = ARTICLE * 3, **metadata) -> SimpleNamespace:
    meta = {"title": "Earthquake near Dhaka", "published_time": "2026-08-16T04:00:00Z"}
    meta.update(metadata)
    return SimpleNamespace(markdown=markdown, metadata=SimpleNamespace(**meta))


def patch_sdk(search_result, scrape_result):
    """Patch both SDK calls. Each may be a value, a list of side effects, or an exception."""

    def as_mock(value):
        if isinstance(value, list) or isinstance(value, BaseException):
            return AsyncMock(side_effect=value)
        return AsyncMock(return_value=value)

    return (
        patch(SEARCH_TARGET, as_mock(search_result)),
        patch(SCRAPE_TARGET, as_mock(scrape_result)),
    )


async def run_research(service, queries, search_result, scrape_result, **kwargs):
    search_patch, scrape_patch = patch_sdk(search_result, scrape_result)
    with search_patch, scrape_patch:
        return await service.research(queries, **kwargs)


# --- happy path -------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_normalises_every_source() -> None:
    service = FirecrawlService(make_settings())
    bundle = await run_research(
        service,
        ["Dhaka earthquake", "ঢাকায় ভূমিকম্প"],
        search_data(web=[web_hit("https://www.thedailystar.net/news/quake")]),
        document(),
    )

    assert len(bundle.sources) == 1
    source = bundle.sources[0]
    assert source.title == "Earthquake near Dhaka"
    assert source.url == "https://www.thedailystar.net/news/quake"
    assert source.domain == "thedailystar.net"
    assert source.published_date == "2026-08-16T04:00:00Z"
    assert source.source_type is SourceType.NEWS
    assert source.content
    assert bundle.has_evidence
    assert bundle.total_content_chars == len(source.content)


@pytest.mark.asyncio
async def test_all_queries_are_searched_concurrently() -> None:
    service = FirecrawlService(make_settings())
    queries = ["query one", "query two", "query three"]
    search_mock = AsyncMock(return_value=search_data(web=[web_hit("https://bbc.com/a")]))

    with patch(SEARCH_TARGET, search_mock), patch(
        SCRAPE_TARGET, AsyncMock(return_value=document())
    ):
        bundle = await service.research(queries)

    assert search_mock.await_count == 3
    assert bundle.queries_used == queries


@pytest.mark.asyncio
async def test_scrape_requests_clean_markdown_only() -> None:
    service = FirecrawlService(make_settings())
    scrape_mock = AsyncMock(return_value=document())

    with patch(
        SEARCH_TARGET,
        AsyncMock(return_value=search_data(web=[web_hit("https://bbc.com/a")])),
    ), patch(SCRAPE_TARGET, scrape_mock):
        await service.research(["q"])

    kwargs = scrape_mock.await_args.kwargs
    assert kwargs["formats"] == ["markdown"]
    assert kwargs["only_main_content"] is True


@pytest.mark.asyncio
async def test_content_is_cleaned_of_page_furniture() -> None:
    service = FirecrawlService(make_settings())
    noisy = "Accept all cookies\nShare this\n" + ARTICLE * 3
    bundle = await run_research(
        service,
        ["q"],
        search_data(web=[web_hit("https://bbc.com/a")]),
        document(markdown=noisy),
    )

    assert "cookies" not in bundle.sources[0].content
    assert "earthquake" in bundle.sources[0].content.lower()


# --- de-duplication and selection -------------------------------------------


@pytest.mark.asyncio
async def test_same_article_from_many_queries_is_scraped_once() -> None:
    """The whole point of canonical de-duplication: one page, one scrape credit."""
    service = FirecrawlService(make_settings())
    duplicates = [
        search_data(web=[web_hit("https://www.bbc.com/news/a")]),
        search_data(web=[web_hit("http://bbc.com/news/a/")]),
        search_data(web=[web_hit("https://bbc.com/news/a?utm_source=twitter")]),
    ]
    scrape_mock = AsyncMock(return_value=document())

    with patch(SEARCH_TARGET, AsyncMock(side_effect=duplicates)), patch(
        SCRAPE_TARGET, scrape_mock
    ):
        bundle = await service.research(["a", "b", "c"])

    assert scrape_mock.await_count == 1
    assert len(bundle.sources) == 1
    assert bundle.candidates_found == 3


@pytest.mark.asyncio
async def test_duplicate_merge_keeps_the_richer_metadata() -> None:
    service = FirecrawlService(make_settings())
    results = [
        search_data(web=[web_hit("https://bbc.com/a", title="", description="short")]),
        search_data(news=[news_hit("https://bbc.com/a", date="2026-08-16")]),
    ]

    with patch(SEARCH_TARGET, AsyncMock(side_effect=results)), patch(
        SCRAPE_TARGET, AsyncMock(return_value=document(published_time=""))
    ):
        bundle = await service.research(["a", "b"])

    assert bundle.sources[0].published_date == "2026-08-16"


@pytest.mark.asyncio
async def test_per_domain_cap_protects_viewpoint_diversity() -> None:
    service = FirecrawlService(make_settings(firecrawl_max_per_domain=2, firecrawl_max_sources=6))
    hits = [web_hit(f"https://bbc.com/news/{i}") for i in range(5)]
    hits += [web_hit("https://reuters.com/a"), web_hit("https://prothomalo.com/b")]

    bundle = await run_research(service, ["q"], search_data(web=hits), document())

    domains = [source.domain for source in bundle.sources]
    assert domains.count("bbc.com") == 2
    assert "reuters.com" in domains
    assert "prothomalo.com" in domains


@pytest.mark.asyncio
async def test_per_domain_cap_is_hard_even_if_that_means_fewer_sources() -> None:
    """A configured maximum that quietly stretches is worse than a short result set."""
    service = FirecrawlService(make_settings(firecrawl_max_per_domain=1, firecrawl_max_sources=3))
    hits = [web_hit(f"https://bbc.com/news/{i}") for i in range(3)]

    bundle = await run_research(service, ["q"], search_data(web=hits), document())

    assert len(bundle.sources) == 1


@pytest.mark.asyncio
async def test_max_sources_is_respected() -> None:
    service = FirecrawlService(make_settings(firecrawl_max_sources=2, firecrawl_max_per_domain=5))
    hits = [web_hit(f"https://site{i}.com/a") for i in range(10)]
    scrape_mock = AsyncMock(return_value=document())

    with patch(
        SEARCH_TARGET, AsyncMock(return_value=search_data(web=hits))
    ), patch(SCRAPE_TARGET, scrape_mock):
        bundle = await service.research(["q"])

    assert scrape_mock.await_count == 2
    assert len(bundle.sources) == 2


@pytest.mark.asyncio
async def test_credible_sources_are_ranked_above_social_media() -> None:
    service = FirecrawlService(make_settings())
    hits = [
        web_hit("https://facebook.com/post/1"),
        web_hit("https://rumorscanner.com/fact/1"),
        web_hit("https://randomblog.wordpress.com/1"),
        web_hit("https://thedailystar.net/a"),
    ]

    bundle = await run_research(service, ["q"], search_data(web=hits), document())

    ordered = [source.domain for source in bundle.sources]
    assert ordered[0] == "rumorscanner.com"
    assert ordered.index("thedailystar.net") < ordered.index("facebook.com")


@pytest.mark.asyncio
async def test_source_types_are_classified() -> None:
    service = FirecrawlService(make_settings())
    hits = [
        web_hit("https://rumorscanner.com/f/1"),
        web_hit("https://bmd.gov.bd/report"),
        web_hit("https://en.wikipedia.org/wiki/Dhaka"),
        web_hit("https://facebook.com/p/1"),
    ]

    bundle = await run_research(service, ["q"], search_data(web=hits), document())

    by_domain = {source.domain: source.source_type for source in bundle.sources}
    assert by_domain["rumorscanner.com"] is SourceType.FACT_CHECK
    assert by_domain["bmd.gov.bd"] is SourceType.GOVERNMENT
    assert by_domain["en.wikipedia.org"] is SourceType.ENCYCLOPEDIA
    assert by_domain["facebook.com"] is SourceType.SOCIAL


# --- length control ---------------------------------------------------------


@pytest.mark.asyncio
async def test_content_is_capped_per_source() -> None:
    service = FirecrawlService(make_settings(firecrawl_max_chars_per_source=500))
    bundle = await run_research(
        service,
        ["q"],
        search_data(web=[web_hit("https://bbc.com/a")]),
        document(markdown=ARTICLE * 50),
    )

    assert len(bundle.sources[0].content) <= 501


@pytest.mark.asyncio
async def test_total_budget_bounds_the_whole_evidence_set() -> None:
    """Per-source caps do not bound the prompt; six capped sources still add up."""
    service = FirecrawlService(
        make_settings(
            firecrawl_max_chars_per_source=2_000,
            firecrawl_max_total_chars=3_000,
            firecrawl_max_per_domain=5,
        )
    )
    hits = [web_hit(f"https://site{i}.com/a") for i in range(5)]

    bundle = await run_research(
        service, ["q"], search_data(web=hits), document(markdown=ARTICLE * 20)
    )

    assert bundle.total_content_chars <= 3_000
    assert bundle.sources, "the budget must not discard everything"


@pytest.mark.asyncio
async def test_budget_drops_sources_rather_than_leaving_stubs() -> None:
    service = FirecrawlService(
        make_settings(
            firecrawl_max_chars_per_source=1_000,
            firecrawl_max_total_chars=1_100,
            firecrawl_max_per_domain=5,
        )
    )
    hits = [web_hit(f"https://site{i}.com/a") for i in range(4)]

    bundle = await run_research(
        service, ["q"], search_data(web=hits), document(markdown=ARTICLE * 20)
    )

    for source in bundle.sources:
        assert len(source.content) >= MIN_USEFUL_CONTENT_CHARS
    assert any("budget" in failure.reason for failure in bundle.failures)
    assert bundle.degraded is True


# --- missing and partial data -----------------------------------------------


@pytest.mark.asyncio
async def test_missing_publication_date_is_none_not_an_error() -> None:
    service = FirecrawlService(make_settings())
    bundle = await run_research(
        service,
        ["q"],
        search_data(web=[web_hit("https://bbc.com/a")]),
        document(published_time="", dc_date="", modified_time=""),
    )

    assert bundle.sources[0].published_date is None


@pytest.mark.asyncio
async def test_date_falls_back_through_metadata_keys() -> None:
    service = FirecrawlService(make_settings())
    bundle = await run_research(
        service,
        ["q"],
        search_data(web=[web_hit("https://bbc.com/a")]),
        document(published_time="", dc_date="2019-03-04"),
    )

    assert bundle.sources[0].published_date == "2019-03-04"


@pytest.mark.asyncio
async def test_missing_title_falls_back_to_url() -> None:
    service = FirecrawlService(make_settings())
    bundle = await run_research(
        service,
        ["q"],
        search_data(web=[web_hit("https://bbc.com/a", title="")]),
        document(title="", og_title=""),
    )

    assert bundle.sources[0].title == "https://bbc.com/a"


@pytest.mark.asyncio
async def test_dict_shaped_responses_are_accepted() -> None:
    """Mocks and older API responses hand back plain dicts, not models."""
    service = FirecrawlService(make_settings())
    data = {"web": [{"url": "https://bbc.com/a", "title": "Dict title"}], "news": []}
    doc = {"markdown": ARTICLE * 3, "metadata": {"title": "Meta title"}}

    bundle = await run_research(service, ["q"], SimpleNamespace(**data), doc)

    assert bundle.sources[0].title == "Meta title"


@pytest.mark.asyncio
async def test_hits_without_a_usable_url_are_skipped() -> None:
    service = FirecrawlService(make_settings())
    hits = [web_hit(""), SimpleNamespace(url=None, title="x"), web_hit("not-a-url")]

    bundle = await run_research(service, ["q"], search_data(web=hits), document())

    assert bundle.sources == []
    assert bundle.candidates_found == 0


# --- failure handling -------------------------------------------------------


@pytest.mark.asyncio
async def test_no_results_is_an_empty_bundle_not_an_exception() -> None:
    """Finding nothing is a real research outcome; it maps to UNVERIFIED later."""
    service = FirecrawlService(make_settings())
    bundle = await run_research(service, ["obscure query"], search_data(), document())

    assert bundle.sources == []
    assert bundle.has_evidence is False
    assert bundle.degraded is True


@pytest.mark.asyncio
async def test_one_failing_query_does_not_sink_the_others() -> None:
    service = FirecrawlService(make_settings())
    results = [
        FirecrawlError("upstream exploded"),
        search_data(web=[web_hit("https://bbc.com/a")]),
    ]

    with patch(SEARCH_TARGET, AsyncMock(side_effect=results)), patch(
        SCRAPE_TARGET, AsyncMock(return_value=document())
    ):
        bundle = await service.research(["bad query", "good query"])

    assert len(bundle.sources) == 1
    assert bundle.queries_used == ["good query"]
    assert bundle.queries_failed == ["bad query"]
    assert bundle.degraded is True


@pytest.mark.asyncio
async def test_malformed_query_is_skipped_not_fatal() -> None:
    service = FirecrawlService(make_settings())
    results = [BadRequestError("bad query"), search_data(web=[web_hit("https://bbc.com/a")])]

    with patch(SEARCH_TARGET, AsyncMock(side_effect=results)), patch(
        SCRAPE_TARGET, AsyncMock(return_value=document())
    ):
        bundle = await service.research(["bad", "good"])

    assert len(bundle.sources) == 1


@pytest.mark.asyncio
async def test_inaccessible_page_is_recorded_and_the_rest_continue() -> None:
    service = FirecrawlService(make_settings())
    scrapes = [FirecrawlError("403 blocked by paywall"), document()]

    with patch(
        SEARCH_TARGET,
        AsyncMock(
            return_value=search_data(
                web=[web_hit("https://ft.com/paywalled"), web_hit("https://bbc.com/open")]
            )
        ),
    ), patch(SCRAPE_TARGET, AsyncMock(side_effect=scrapes)):
        bundle = await service.research(["q"])

    assert len(bundle.sources) == 1
    assert len(bundle.failures) == 1
    assert bundle.failures[0].reason
    assert bundle.degraded is True


@pytest.mark.asyncio
async def test_thin_page_is_rejected_as_unusable() -> None:
    """Cookie walls and redirect stubs scrape 'successfully' but carry no evidence."""
    service = FirecrawlService(make_settings())
    bundle = await run_research(
        service,
        ["q"],
        search_data(web=[web_hit("https://bbc.com/a")]),
        document(markdown="Enable JavaScript to continue."),
    )

    assert bundle.sources == []
    assert "too little readable content" in bundle.failures[0].reason


@pytest.mark.asyncio
async def test_all_scrapes_failing_yields_empty_degraded_bundle() -> None:
    service = FirecrawlService(make_settings())
    bundle = await run_research(
        service,
        ["q"],
        search_data(web=[web_hit("https://a.com/1"), web_hit("https://b.com/2")]),
        FirecrawlError("blocked"),
    )

    assert bundle.sources == []
    assert len(bundle.failures) == 2
    assert bundle.degraded is True


@pytest.mark.asyncio
async def test_missing_api_key_raises_service_unavailable() -> None:
    service = FirecrawlService(make_settings(firecrawl_api_key=None))

    with pytest.raises(ServiceUnavailableError) as exc:
        await service.research(["q"])

    assert "FIRECRAWL_API_KEY" in exc.value.message


@pytest.mark.asyncio
async def test_missing_api_key_makes_no_network_call() -> None:
    service = FirecrawlService(make_settings(firecrawl_api_key=None))
    search_mock = AsyncMock()

    with patch(SEARCH_TARGET, search_mock):
        with pytest.raises(ServiceUnavailableError):
            await service.research(["q"])

    search_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_query_list_is_rejected() -> None:
    service = FirecrawlService(make_settings())

    with pytest.raises(ServiceError):
        await service.research(["", "   "])


@pytest.mark.asyncio
async def test_unauthorized_is_surfaced_not_degraded() -> None:
    """A bad key breaks every query alike, so hiding it behind an empty bundle
    would send the user hunting for a research failure that is really a config bug."""
    service = FirecrawlService(make_settings())

    with patch(
        SEARCH_TARGET, AsyncMock(side_effect=UnauthorizedError("bad key"))
    ):
        with pytest.raises(ServiceError) as exc:
            await service.research(["q"])

    assert "Firecrawl API key" in exc.value.message


@pytest.mark.asyncio
async def test_payment_required_is_surfaced() -> None:
    service = FirecrawlService(make_settings())

    with patch(
        SEARCH_TARGET,
        AsyncMock(side_effect=PaymentRequiredError("out of credits")),
    ):
        with pytest.raises(ServiceError):
            await service.research(["q"])


@pytest.mark.asyncio
async def test_rate_limit_maps_to_its_own_error() -> None:
    service = FirecrawlService(make_settings())

    with patch(
        SEARCH_TARGET,
        AsyncMock(side_effect=FirecrawlRateLimitError("slow down")),
    ):
        with pytest.raises(RateLimitError) as exc:
            await service.research(["q"])

    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_during_scrape_is_surfaced() -> None:
    service = FirecrawlService(make_settings())

    with patch(
        SEARCH_TARGET,
        AsyncMock(return_value=search_data(web=[web_hit("https://bbc.com/a")])),
    ), patch(
        SCRAPE_TARGET,
        AsyncMock(side_effect=FirecrawlRateLimitError("slow down")),
    ):
        with pytest.raises(RateLimitError):
            await service.research(["q"])


@pytest.mark.asyncio
async def test_api_key_never_appears_in_the_bundle() -> None:
    service = FirecrawlService(make_settings(firecrawl_api_key="super-secret-key"))
    bundle = await run_research(
        service, ["q"], search_data(web=[web_hit("https://bbc.com/a")]), document()
    )

    assert "super-secret-key" not in bundle.model_dump_json()


# --- projection to the API shape --------------------------------------------


@pytest.mark.asyncio
async def test_source_projects_to_the_api_shape() -> None:
    service = FirecrawlService(make_settings())
    bundle = await run_research(
        service, ["q"], search_data(web=[web_hit("https://bbc.com/a")]), document()
    )

    api_source = bundle.sources[0].to_api_source()
    assert api_source.domain == "bbc.com"
    assert api_source.source_type == "news"
    assert api_source.published_date == "2026-08-16T04:00:00Z"
    # Internal-only research fields must not leak into the public contract.
    assert "credibility" not in api_source.model_dump()
    assert "content" not in api_source.model_dump()
