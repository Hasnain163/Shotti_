"""Firecrawl research agent.

Takes the search queries produced by the Gemini claim agent and turns them into a
bundle of cleaned, length-capped, normalised sources. It gathers evidence only —
weighing it is the analysis stage's job.

Shape of the work:

    search all queries concurrently
      -> merge candidates, drop duplicate URLs
      -> rank by publisher reputation, cap per domain for viewpoint diversity
      -> scrape the top N concurrently
      -> clean, cap length, normalise
      -> ResearchBundle

Every stage degrades rather than aborts: a failed query or an unreachable page is
recorded in the bundle and the rest of the research continues.
"""

import asyncio
import logging
from typing import Any

from firecrawl import AsyncFirecrawl
from firecrawl.v2.utils.error_handler import (
    BadRequestError,
    FirecrawlError,
    PaymentRequiredError,
    RateLimitError as FirecrawlRateLimitError,
    UnauthorizedError,
)

from app.config import Settings
from app.models.source import (
    FailedSource,
    ResearchBundle,
    ResearchSource,
    SearchCandidate,
    SourceType,
)
from app.services.domains import classify_domain, credibility_score
from app.utils.errors import (
    RateLimitError,
    ServiceError,
    ServiceUnavailableError,
    ShottiError,
)
from app.utils.text import canonical_url, clean_scraped_text, domain_of, truncate_text

logger = logging.getLogger(__name__)

# Metadata keys that may carry a publication date, best first.
_DATE_KEYS = (
    "published_time",
    "article_published_time",
    "dc_date",
    "dc_terms_created",
    "dc_date_created",
    "modified_time",
)

# Content shorter than this is a paywall notice, a cookie wall, or a redirect stub
# rather than an article, and only adds noise to the analysis prompt.
MIN_USEFUL_CONTENT_CHARS = 200


class FirecrawlService:
    """Thin wrapper around the Firecrawl SDK.

    The client is built lazily so the app still starts, and /api/health still
    answers, with no Firecrawl key configured.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AsyncFirecrawl | None = None
        # Throttles our own concurrency. Without it a single claim's burst of
        # searches and scrapes trips the provider's per-minute rate limit, which
        # then fails requests that would otherwise have succeeded.
        self._slots = asyncio.Semaphore(max(1, settings.firecrawl_max_concurrent_requests))

    @property
    def client(self) -> AsyncFirecrawl:
        if not self._settings.firecrawl_api_key:
            raise ServiceUnavailableError(
                "Web research is unavailable because FIRECRAWL_API_KEY is not configured."
            )
        if self._client is None:
            # Key comes from settings, which reads the environment. Never inlined.
            self._client = AsyncFirecrawl(api_key=self._settings.firecrawl_api_key)
        return self._client

    # --- public API ---------------------------------------------------------

    async def research(
        self,
        queries: list[str],
        max_sources: int | None = None,
    ) -> ResearchBundle:
        """Search, fetch, and normalise evidence for a set of queries.

        Returns an empty-but-valid bundle when nothing is found; that is a real
        research outcome (it maps to UNVERIFIED later), not an error.

        Raises:
            ServiceUnavailableError: no API key configured.
            RateLimitError: Firecrawl quota or rate limit reached.
            ServiceError: authentication or billing failure — nothing will work
                until it is fixed, so it is not degraded into an empty bundle.
        """
        usable_queries = [query.strip() for query in queries if query and query.strip()]
        if not usable_queries:
            raise ServiceError("Cannot research a claim without any search queries.")

        # Fail fast on a missing key rather than inside a gathered task.
        _ = self.client

        limit = max_sources or self._settings.firecrawl_max_sources
        bundle = ResearchBundle(queries_used=[])

        candidates = await self._search_all(usable_queries, bundle)
        bundle.candidates_found = len(candidates)
        if not candidates:
            logger.info("research found no candidates for %d queries", len(usable_queries))
            bundle.degraded = True
            return bundle

        selected = self._select_candidates(candidates, limit)
        logger.info(
            "research selected %d of %d candidates across %d queries",
            len(selected),
            len(candidates),
            len(bundle.queries_used),
        )

        await self._scrape_all(selected, bundle)

        # Highest-reputation sources first so prompt truncation, if it ever bites,
        # drops the weakest evidence rather than the strongest.
        bundle.sources.sort(key=lambda source: source.credibility, reverse=True)
        self._apply_total_budget(bundle)
        bundle.total_content_chars = sum(len(source.content) for source in bundle.sources)

        if bundle.failures or bundle.queries_failed or not bundle.sources:
            bundle.degraded = True
        return bundle

    async def aclose(self) -> None:
        """Release the SDK's HTTP connections."""
        client = self._client
        self._client = None
        if client is None:
            return
        for attr in ("aclose", "close"):
            closer = getattr(client, attr, None)
            if closer is None:
                continue
            try:
                result = closer()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # cleanup must never mask a real error
                logger.debug("Firecrawl client cleanup via %s() failed", attr)
            return

    # --- search ------------------------------------------------------------

    async def _search_all(
        self, queries: list[str], bundle: ResearchBundle
    ) -> list[SearchCandidate]:
        """Run every query concurrently and merge the hits.

        Serial search is the single biggest avoidable latency in the pipeline, so
        these always run together. One failing query must not sink the others.
        """
        results = await asyncio.gather(
            *(self._search_one(query) for query in queries),
            return_exceptions=True,
        )

        merged: list[SearchCandidate] = []
        for query, result in zip(queries, results, strict=True):
            if isinstance(result, ShottiError):
                # Auth, billing, and rate limits affect every query alike, so there
                # is nothing to degrade into — surface them.
                raise result
            if isinstance(result, BaseException) or result is None:
                # None means _search_one handled a provider error. Either way the
                # query produced nothing usable and must not be reported as used —
                # "failed" and "found nothing" lead to different conclusions later.
                logger.warning("search failed for %r: %s", query, result)
                bundle.queries_failed.append(query)
                continue
            bundle.queries_used.append(query)
            merged.extend(result)
        return merged

    async def _search_one(self, query: str) -> list[SearchCandidate] | None:
        """Search one query.

        Returns normalised candidates, an empty list when the query genuinely found
        nothing, or None when the query itself failed.
        """
        try:
            async with self._slots:
                data = await self.client.search(
                    query,
                    limit=self._settings.firecrawl_search_limit,
                    # News results carry dates, which plain web results usually lack.
                    sources=["web", "news"],
                    timeout=self._settings.firecrawl_search_timeout_ms,
                )
        except (UnauthorizedError, PaymentRequiredError) as exc:
            logger.error("Firecrawl rejected our credentials or billing: %s", exc)
            raise ServiceError(
                "Web research is not authorised. Check the Firecrawl API key and plan."
            ) from exc
        except FirecrawlRateLimitError as exc:
            logger.warning("Firecrawl rate limit hit during search: %s", exc)
            raise RateLimitError(
                "The web research service rate limit was reached. Please wait a moment "
                "and try again."
            ) from exc
        except BadRequestError as exc:
            # One malformed query should not sink the whole research run.
            logger.warning("Firecrawl rejected query %r: %s", query, exc)
            return None
        except FirecrawlError as exc:
            logger.warning("Firecrawl search error for %r: %s", query, exc)
            return None
        except Exception as exc:
            logger.warning("Unexpected search failure for %r: %s", query, exc)
            return None

        candidates: list[SearchCandidate] = []
        for bucket, is_news in (("web", False), ("news", True)):
            for item in _as_list(getattr(data, bucket, None)):
                candidate = self._to_candidate(item, query, from_news=is_news)
                if candidate is not None:
                    candidates.append(candidate)
        return candidates

    def _to_candidate(
        self, item: Any, query: str, from_news: bool
    ) -> SearchCandidate | None:
        """Normalise one search hit. Returns None when it has no usable URL."""
        url = _get(item, "url")
        if not isinstance(url, str) or not url.strip():
            return None

        domain = domain_of(url)
        if not domain:
            return None

        source_type = classify_domain(domain)
        # A hit from the news bucket on an unclassified domain is still a news site.
        if from_news and source_type is SourceType.OTHER:
            source_type = SourceType.NEWS

        return SearchCandidate(
            url=url.strip(),
            title=_as_text(_get(item, "title")),
            snippet=_as_text(_get(item, "snippet") or _get(item, "description")),
            published_date=_as_text(_get(item, "date")) or None,
            source_type=source_type,
            domain=domain,
            found_by_query=query,
            credibility=credibility_score(domain, source_type),
        )

    # --- selection ---------------------------------------------------------

    def _select_candidates(
        self, candidates: list[SearchCandidate], limit: int
    ) -> list[SearchCandidate]:
        """De-duplicate, then pick the best candidates to spend scrapes on.

        Duplicates are collapsed on a canonical URL, so the same article found by
        three different queries costs one scrape. Per-domain capping matters as much
        as ranking: eight pages from one outlet look like eight sources but carry a
        single viewpoint.

        The per-domain cap is hard. When there are not enough distinct publishers to
        fill the budget we return fewer sources rather than padding with more pages
        from one outlet — a configured maximum that quietly stretches is worse than a
        short result set, and over-weighting one publisher skews the analysis.
        """
        best_by_url: dict[str, SearchCandidate] = {}
        for candidate in candidates:
            key = canonical_url(candidate.url)
            existing = best_by_url.get(key)
            if existing is None:
                best_by_url[key] = candidate
                continue
            # Same page seen twice: keep whichever copy carries more information.
            if candidate.published_date and not existing.published_date:
                existing.published_date = candidate.published_date
            if len(candidate.snippet) > len(existing.snippet):
                existing.snippet = candidate.snippet
            if not existing.title and candidate.title:
                existing.title = candidate.title

        ordered = sorted(
            best_by_url.values(),
            key=lambda candidate: (candidate.credibility, len(candidate.snippet)),
            reverse=True,
        )

        per_domain = self._settings.firecrawl_max_per_domain
        selected: list[SearchCandidate] = []
        domain_counts: dict[str, int] = {}

        for candidate in ordered:
            if len(selected) >= limit:
                break
            count = domain_counts.get(candidate.domain, 0)
            if count >= per_domain:
                continue
            domain_counts[candidate.domain] = count + 1
            selected.append(candidate)

        return selected

    # --- scrape ------------------------------------------------------------

    async def _scrape_all(
        self, candidates: list[SearchCandidate], bundle: ResearchBundle
    ) -> None:
        """Fetch all selected pages concurrently, recording failures."""
        results = await asyncio.gather(
            *(self._scrape_one(candidate) for candidate in candidates),
            return_exceptions=True,
        )

        for candidate, result in zip(candidates, results, strict=True):
            if isinstance(result, ShottiError):
                raise result
            if isinstance(result, BaseException):
                logger.warning("scrape failed for %s: %s", candidate.url, result)
                bundle.failures.append(
                    FailedSource(
                        url=candidate.url,
                        domain=candidate.domain,
                        reason="The page could not be fetched.",
                    )
                )
                continue
            source, failure = result
            if source is not None:
                bundle.sources.append(source)
            elif failure is not None:
                bundle.failures.append(failure)

    async def _scrape_one(
        self, candidate: SearchCandidate
    ) -> tuple[ResearchSource | None, FailedSource | None]:
        """Fetch and normalise one page.

        Returns ``(source, None)`` on success and ``(None, failure)`` when the page
        is unusable. Only errors that affect the whole run are raised.
        """
        try:
            async with self._slots:
                document = await self.client.scrape(
                    candidate.url,
                    formats=["markdown"],
                    only_main_content=True,
                    timeout=self._settings.firecrawl_scrape_timeout_ms,
                    block_ads=True,
                    remove_base64_images=True,
                )
        except (UnauthorizedError, PaymentRequiredError) as exc:
            logger.error("Firecrawl rejected our credentials or billing: %s", exc)
            raise ServiceError(
                "Web research is not authorised. Check the Firecrawl API key and plan."
            ) from exc
        except FirecrawlRateLimitError as exc:
            logger.warning("Firecrawl rate limit hit during scrape: %s", exc)
            raise RateLimitError(
                "The web research service rate limit was reached. Please wait a moment "
                "and try again."
            ) from exc
        except FirecrawlError as exc:
            # Paywalls, bot walls, 404s, timeouts. Expected at this scale.
            logger.info("could not scrape %s: %s", candidate.url, exc)
            return None, FailedSource(
                url=candidate.url,
                domain=candidate.domain,
                reason="The page could not be fetched.",
            )
        except Exception as exc:
            logger.warning("unexpected scrape failure for %s: %s", candidate.url, exc)
            return None, FailedSource(
                url=candidate.url,
                domain=candidate.domain,
                reason="The page could not be fetched.",
            )

        content = truncate_text(
            clean_scraped_text(_as_text(_get(document, "markdown"))),
            self._settings.firecrawl_max_chars_per_source,
        )
        if len(content) < MIN_USEFUL_CONTENT_CHARS:
            return None, FailedSource(
                url=candidate.url,
                domain=candidate.domain,
                reason="The page returned too little readable content to use.",
            )

        metadata = _get(document, "metadata")
        return (
            ResearchSource(
                title=self._pick_title(metadata, candidate),
                url=candidate.url,
                domain=candidate.domain,
                published_date=candidate.published_date or _pick_date(metadata),
                content=content,
                source_type=candidate.source_type,
                snippet=truncate_text(candidate.snippet, 300),
                found_by_query=candidate.found_by_query,
                credibility=candidate.credibility,
            ),
            None,
        )

    @staticmethod
    def _pick_title(metadata: Any, candidate: SearchCandidate) -> str:
        """Best available title, falling back to the URL so it is never blank."""
        for value in (
            _as_text(_get(metadata, "title")),
            _as_text(_get(metadata, "og_title")),
            candidate.title,
        ):
            if value:
                return truncate_text(value, 300)
        return candidate.url

    # --- budget ------------------------------------------------------------

    def _apply_total_budget(self, bundle: ResearchBundle) -> None:
        """Keep the whole evidence set inside a total character budget.

        The per-source cap alone does not bound the prompt: six capped sources still
        add up. Weakest sources are trimmed first, and any source squeezed below the
        useful minimum is dropped outright rather than left as a stub.
        """
        budget = self._settings.firecrawl_max_total_chars
        remaining = budget
        kept: list[ResearchSource] = []

        for source in bundle.sources:  # already sorted strongest first
            if remaining < MIN_USEFUL_CONTENT_CHARS:
                bundle.failures.append(
                    FailedSource(
                        url=source.url,
                        domain=source.domain,
                        reason="Dropped to stay within the evidence size budget.",
                    )
                )
                continue
            if len(source.content) > remaining:
                source.content = truncate_text(source.content, remaining)
            remaining -= len(source.content)
            kept.append(source)

        bundle.sources = kept


# --- helpers ---------------------------------------------------------------
# The SDK returns pydantic models, but mocked tests and older responses may hand
# back plain dicts. Reading both shapes keeps the service tolerant either way.


def _get(obj: Any, key: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return []


def _as_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _pick_date(metadata: Any) -> str | None:
    """First usable publication date in the metadata. None when absent."""
    for key in _DATE_KEYS:
        value = _as_text(_get(metadata, key))
        if value:
            return value
    return None
