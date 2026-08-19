"""The verification pipeline.

    claim
      -> Gemini claim analysis        (understand, generate search queries)
      -> Firecrawl research           (search, scrape, normalise sources)
      -> Gemini evidence analysis     (stance, reliability, dates, verdict)
      -> verdict validation           (grounding, coherence)
      -> VerifyResponse

This module owns the stage order and nothing else. Each stage's own service handles
its errors; what happens here is deciding when a stage's failure should end the
request and when the pipeline should carry on with less.

Two rules shape every decision below:

* No stage may invent evidence. Sources come from Firecrawl, quotes are checked
  against the text Firecrawl actually retrieved, and URLs come from our own records.
* Insufficient evidence is reported as UNVERIFIED with the reason, never dressed up
  as a verdict.
"""

import asyncio
import hashlib
import logging
import time
from datetime import date

from app.config import Settings
from app.models.analysis import EvidenceAnalysis
from app.models.claim import ClaimAnalysis
from app.models.source import ResearchBundle
from app.models.verify import (
    MAX_CLAIM_LENGTH,
    ScreenshotVerifyResponse,
    Verdict,
    VerifyMeta,
    VerifyRequest,
    VerifyResponse,
)
from app.services.cache import TTLCache
from app.services.firecrawl import FirecrawlService
from app.services.gemini import GeminiService
from app.utils.errors import ServiceError
from app.utils.text import truncate_text

logger = logging.getLogger(__name__)

# Leaves room for the ellipsis truncate_text may append, so a response claim can
# always be fed back through VerifyRequest without tripping its max_length.
MAX_RESPONSE_CLAIM_CHARS = MAX_CLAIM_LENGTH - 10


def make_claim_id(claim: str) -> str:
    """Stable short id for a claim, so the same question maps to the same result."""
    return hashlib.sha256(claim.strip().lower().encode("utf-8")).hexdigest()[:16]


class VerificationPipeline:
    """Runs a claim through all stages and assembles the API response."""

    def __init__(
        self,
        settings: Settings,
        gemini: GeminiService,
        firecrawl: FirecrawlService,
        cache: TTLCache[VerifyResponse] | None = None,
    ) -> None:
        self._settings = settings
        self._gemini = gemini
        self._firecrawl = firecrawl
        self._cache = cache

    async def verify(self, request: VerifyRequest, today: date | None = None) -> VerifyResponse:
        """Verify one claim end to end.

        Raises:
            ServiceUnavailableError: a required integration is not configured.
            RateLimitError: an upstream quota was reached; the caller should retry.
            ServiceError: an upstream stage failed in a way that cannot be degraded.
        """
        claim_id = make_claim_id(request.claim)
        started = time.perf_counter()
        logger.info(
            "[%s] verification started: language=%s chars=%d",
            claim_id,
            request.language.value,
            len(request.claim),
        )

        cached = self._cache.get(claim_id) if self._cache else None
        if cached is not None:
            logger.info("[%s] served from cache; no API quota spent", claim_id)
            # Copied so a caller mutating the response cannot corrupt the cache, and
            # flagged as cached so the timing shown to the user stays truthful.
            return cached.model_copy(
                update={"meta": cached.meta.model_copy(update={"cached": True})}
            )

        try:
            async with asyncio.timeout(self._settings.pipeline_timeout_seconds):
                response = await self._run(request, claim_id, started, today)
            if self._cache is not None:
                self._cache.set(claim_id, response)
            return response
        except TimeoutError as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            logger.error("[%s] verification timed out after %dms", claim_id, elapsed)
            raise ServiceError(
                "Verification took too long to complete. Please try again."
            ) from exc

    async def verify_screenshot(
        self,
        image_bytes: bytes,
        mime_type: str,
        today: date | None = None,
    ) -> ScreenshotVerifyResponse:
        """Read a screenshot, then verify the claim it contains.

        The image adds one stage on the front; everything after it is the same code
        path as a typed claim, so there is exactly one verdict system.
        """
        started = time.perf_counter()
        logger.info("screenshot verification started: %s, %d bytes", mime_type, len(image_bytes))

        # The timeout has to cover reading the image as well as verifying the claim.
        # Bounding only the inner verify() would allow retried image reads to add a
        # second full budget on top, which is how a request ends up hanging past three
        # minutes — long past the point a user has given up.
        try:
            async with asyncio.timeout(self._settings.pipeline_timeout_seconds):
                return await self._run_screenshot(image_bytes, mime_type, started, today)
        except TimeoutError as exc:
            logger.error(
                "screenshot verification timed out after %dms", _elapsed_ms(started)
            )
            raise ServiceError(
                "Reading and checking that image took too long. Please try again."
            ) from exc

    async def _run_screenshot(
        self,
        image_bytes: bytes,
        mime_type: str,
        started: float,
        today: date | None,
    ) -> ScreenshotVerifyResponse:
        extraction = await self._gemini.extract_claim_from_image(
            image_bytes=image_bytes, mime_type=mime_type
        )

        # No claim in the image means there is nothing to research. Returning
        # UNVERIFIED here is honest and costs no further API calls. The length check
        # also keeps a stray one-word extraction out of VerifyRequest, whose own
        # minimum would otherwise raise a validation error from deep in the pipeline.
        if not extraction.has_factual_claim or len(extraction.primary_claim.strip()) < 3:
            logger.info("screenshot contains no checkable claim; skipping verification")
            reason = extraction.notes or (
                "No factual claim could be read from this image."
            )
            placeholder = extraction.primary_claim or extraction.extracted_text or "(no text)"
            return ScreenshotVerifyResponse(
                **self._unresearched_response(
                    claim=placeholder,
                    language=extraction.language.value,
                    explanation=reason,
                    context=[
                        "Only factual claims can be checked against sources. "
                        "You can edit the text and try again."
                    ],
                    started=started,
                ).model_dump(),
                extraction=extraction,
            )

        # Hand the extracted claim to the ordinary pipeline. Language is left as
        # 'auto' rather than forced from the image read, so claim analysis detects it
        # from the text itself and the two stages cannot disagree.
        request = VerifyRequest(claim=extraction.primary_claim)
        logger.info("screenshot claim extracted; entering standard pipeline")

        verification = await self.verify(request, today=today)

        return ScreenshotVerifyResponse(
            **verification.model_dump(),
            extraction=extraction,
        )

    async def _run(
        self,
        request: VerifyRequest,
        claim_id: str,
        started: float,
        today: date | None,
    ) -> VerifyResponse:
        # --- stage 1: understand the claim ---------------------------------
        stage_started = time.perf_counter()
        claim_analysis = await self._gemini.analyze_claim(
            claim=request.claim,
            requested_language=request.language.value,
            today=today,
        )
        logger.info(
            "[%s] claim analysed in %dms: lang=%s topic=%s checkable=%s queries=%d",
            claim_id,
            _elapsed_ms(stage_started),
            claim_analysis.language.value,
            claim_analysis.topic.value,
            claim_analysis.is_checkable,
            len(claim_analysis.search_queries),
        )

        # Nothing could settle an opinion or a prediction, so stop before spending
        # research credits on it.
        if not claim_analysis.is_checkable:
            logger.info("[%s] claim is not checkable; skipping research", claim_id)
            return self._build_response(
                request=request,
                claim_id=claim_id,
                claim_analysis=claim_analysis,
                bundle=ResearchBundle(degraded=True),
                analysis=EvidenceAnalysis.unverified(
                    explanation=(
                        claim_analysis.uncheckable_reason
                        or "This statement cannot be fact-checked against evidence."
                    ),
                    context=["Only factual claims can be verified against sources."],
                ),
                started=started,
            )

        if not claim_analysis.search_queries:
            # Defensive: the prompt asks for queries, so this means a degraded response.
            logger.warning("[%s] claim analysis produced no search queries", claim_id)
            return self._build_response(
                request=request,
                claim_id=claim_id,
                claim_analysis=claim_analysis,
                bundle=ResearchBundle(degraded=True),
                analysis=EvidenceAnalysis.unverified(
                    explanation=(
                        "This claim could not be turned into a web search, so no "
                        "evidence was gathered and it cannot be verified."
                    ),
                    context=["No search queries could be generated for this claim."],
                ),
                started=started,
            )

        # --- stage 2: gather evidence --------------------------------------
        stage_started = time.perf_counter()
        bundle = await self._firecrawl.research(claim_analysis.search_queries)
        logger.info(
            "[%s] research finished in %dms: %d/%d sources, %d failures, degraded=%s",
            claim_id,
            _elapsed_ms(stage_started),
            len(bundle.sources),
            bundle.candidates_found,
            len(bundle.failures),
            bundle.degraded,
        )

        # --- stage 3: weigh the evidence -----------------------------------
        # With no sources this returns UNVERIFIED without calling Gemini, so the
        # model is never asked to judge a claim it has no evidence for.
        stage_started = time.perf_counter()
        analysis = await self._gemini.analyze_evidence(
            claim_analysis=claim_analysis,
            sources=bundle.sources,
            today=today,
        )
        logger.info(
            "[%s] evidence analysed in %dms: verdict=%s confidence=%.2f dropped=%d",
            claim_id,
            _elapsed_ms(stage_started),
            analysis.verdict.value,
            analysis.confidence_score,
            analysis.dropped_evidence_count,
        )
        if analysis.dropped_evidence_count:
            logger.warning(
                "[%s] %d quote(s) discarded as ungrounded",
                claim_id,
                analysis.dropped_evidence_count,
            )

        # --- stage 4: assemble the response --------------------------------
        response = self._build_response(
            request=request,
            claim_id=claim_id,
            claim_analysis=claim_analysis,
            bundle=bundle,
            analysis=analysis,
            started=started,
        )
        logger.info(
            "[%s] verification complete in %dms: verdict=%s confidence=%.2f sources=%d",
            claim_id,
            response.meta.duration_ms,
            response.verdict.value,
            response.confidence_score,
            len(response.sources),
        )
        return response

    def _unresearched_response(
        self,
        claim: str,
        language: str,
        explanation: str,
        context: list[str],
        started: float,
    ) -> VerifyResponse:
        """An UNVERIFIED response for input that was never researched.

        Used when there is nothing researchable — no claim in an image, no queries
        generated. Zero confidence and no sources, so it can never read as a verdict.
        """
        trimmed = truncate_text(claim.strip(), MAX_RESPONSE_CLAIM_CHARS) or "(no text)"
        return VerifyResponse(
            claim=trimmed,
            normalized_claim=trimmed,
            verdict=Verdict.UNVERIFIED,
            confidence_score=0.0,
            explanation=explanation,
            supporting_evidence=[],
            contradicting_evidence=[],
            important_context=context,
            sources=[],
            claim_id=make_claim_id(trimmed),
            language=language,
            source_assessments=[],
            meta=VerifyMeta(duration_ms=_elapsed_ms(started), degraded=True),
        )

    def _build_response(
        self,
        request: VerifyRequest,
        claim_id: str,
        claim_analysis: ClaimAnalysis,
        bundle: ResearchBundle,
        analysis: EvidenceAnalysis,
        started: float,
    ) -> VerifyResponse:
        """Project internal models onto the public contract.

        Only ``to_api_source`` output reaches the client, so scraped page content and
        internal ranking scores stay server-side, and every URL is one we retrieved.
        """
        return VerifyResponse(
            claim=request.claim,
            normalized_claim=claim_analysis.normalized_claim,
            verdict=analysis.verdict,
            confidence_score=analysis.confidence_score,
            explanation=analysis.short_explanation,
            supporting_evidence=analysis.supporting_evidence,
            contradicting_evidence=analysis.contradicting_evidence,
            important_context=analysis.important_context,
            sources=[source.to_api_source() for source in bundle.sources],
            claim_id=claim_id,
            language=claim_analysis.language.value,
            source_assessments=analysis.source_assessments,
            meta=VerifyMeta(
                duration_ms=_elapsed_ms(started),
                sources_found=bundle.candidates_found,
                sources_used=len(bundle.sources),
                queries_used=len(bundle.queries_used),
                dropped_evidence_count=analysis.dropped_evidence_count,
                has_conflicting_evidence=analysis.has_conflicting_evidence,
                relies_on_speculation=analysis.relies_on_speculation,
                degraded=bundle.degraded or analysis.dropped_evidence_count > 0,
            ),
        )


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
