"""Gemini integration.

Two stages live here: claim analysis (understand the claim) and evidence analysis
(decide the verdict). Vision and chat will be added as further methods so there is
exactly one place that knows how to talk to Gemini.
"""

import asyncio
import logging
from datetime import date
from typing import TypeVar

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.models.analysis import EvidenceAnalysis, GeminiVerdictPayload
from app.models.claim import ClaimAnalysis, GeminiClaimPayload
from app.models.source import ResearchSource
from app.prompts.analyze import (
    EVIDENCE_ANALYSIS_SYSTEM_PROMPT,
    build_evidence_analysis_prompt,
)
from app.models.screenshot import GeminiScreenshotPayload, ScreenshotExtraction
from app.prompts.normalize import (
    CLAIM_ANALYSIS_SYSTEM_PROMPT,
    build_claim_analysis_prompt,
)
from app.prompts.screenshot import (
    SCREENSHOT_EXTRACTION_SYSTEM_PROMPT,
    SCREENSHOT_USER_PROMPT,
)
from app.utils.errors import (
    RateLimitError,
    ServiceError,
    ServiceUnavailableError,
    ShottiError,
)

logger = logging.getLogger(__name__)

PayloadT = TypeVar("PayloadT", bound=BaseModel)


class GeminiService:
    """Thin wrapper around the Google Gemini SDK.

    The client is created lazily so the app can start, and /api/health can answer,
    without a Gemini key present.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if not self._settings.gemini_api_key:
            raise ServiceUnavailableError(
                "Claim analysis is unavailable because GEMINI_API_KEY is not configured."
            )
        if self._client is None:
            # Key comes from settings, which reads the environment. Never inlined.
            self._client = genai.Client(api_key=self._settings.gemini_api_key)
        return self._client

    async def aclose(self) -> None:
        """Release the SDK's underlying HTTP connections.

        Called on app shutdown, and by tests, so the SDK does not leave an
        unawaited cleanup coroutine behind when the client is garbage collected.
        """
        if self._client is not None:
            await self._client.aio.aclose()
            self._client = None

    async def analyze_claim(
        self,
        claim: str,
        requested_language: str = "auto",
        today: date | None = None,
    ) -> ClaimAnalysis:
        """Understand a claim and produce an investigation plan.

        Returns no verdict by design — see ``ClaimAnalysis``.

        Raises:
            ServiceUnavailableError: no API key configured.
            ServiceError: Gemini failed, timed out, or returned an unusable shape.
        """
        # Resolve the client up front: it raises ServiceUnavailableError when no key
        # is configured, and that must not be caught by the broad handler below.
        client = self.client

        prompt = build_claim_analysis_prompt(
            claim=claim,
            today=(today or date.today()).isoformat(),
            requested_language=requested_language,
        )

        config = self._build_config(CLAIM_ANALYSIS_SYSTEM_PROMPT, GeminiClaimPayload)

        response = await self._generate_with_retry(client, prompt, config)
        payload = self._extract_payload(response, GeminiClaimPayload)
        try:
            analysis = ClaimAnalysis.from_payload(payload, original_claim=claim.strip())
        except ValidationError as exc:
            logger.error("claim analysis failed strict validation: %s", exc)
            raise ServiceError(
                "The AI service returned an incomplete claim analysis. Please try again."
            ) from exc

        logger.info(
            "claim analysed: lang=%s topic=%s checkable=%s queries=%d",
            analysis.language,
            analysis.topic,
            analysis.is_checkable,
            len(analysis.search_queries),
        )
        return analysis

    async def analyze_evidence(
        self,
        claim_analysis: ClaimAnalysis,
        sources: list[ResearchSource],
        today: date | None = None,
    ) -> EvidenceAnalysis:
        """Weigh the retrieved evidence against the claim and decide the verdict.

        With no sources this returns UNVERIFIED without calling Gemini at all: there
        is nothing to analyse, and asking the model anyway would invite it to answer
        from memory — exactly the failure this stage exists to prevent.

        Raises:
            ServiceUnavailableError: no API key configured.
            RateLimitError: Gemini quota or rate limit reached.
            ServiceError: Gemini failed or returned an unusable shape.
        """
        if not sources:
            logger.info("no sources to analyse; returning UNVERIFIED without calling Gemini")
            return EvidenceAnalysis.unverified(
                explanation=(
                    "No usable sources could be retrieved for this claim, so it cannot "
                    "be verified either way."
                ),
                context=["No web sources were available to check this claim against."],
            )

        client = self.client

        prompt = build_evidence_analysis_prompt(
            analysis=claim_analysis,
            sources=sources,
            today=(today or date.today()).isoformat(),
        )
        config = self._build_config(EVIDENCE_ANALYSIS_SYSTEM_PROMPT, GeminiVerdictPayload)

        response = await self._generate_with_retry(client, prompt, config)
        payload = self._extract_payload(response, GeminiVerdictPayload)

        # from_payload is where quotes are checked against the real scraped text.
        # Its strict validation can still reject the payload — an empty explanation,
        # say — and that must surface as a service error rather than an unhandled 500.
        try:
            analysis = EvidenceAnalysis.from_payload(payload, sources=sources)
        except ValidationError as exc:
            logger.error("evidence analysis failed strict validation: %s", exc)
            raise ServiceError(
                "The AI service returned an incomplete analysis. Please try again."
            ) from exc

        logger.info(
            "evidence analysed: verdict=%s confidence=%.2f support=%d contra=%d "
            "dropped=%d sources=%d",
            analysis.verdict,
            analysis.confidence_score,
            len(analysis.supporting_evidence),
            len(analysis.contradicting_evidence),
            analysis.dropped_evidence_count,
            len(sources),
        )
        return analysis

    async def extract_claim_from_image(
        self,
        image_bytes: bytes,
        mime_type: str,
    ) -> ScreenshotExtraction:
        """Read a screenshot and report the claim it contains.

        Produces no verdict: the extracted claim goes through the same verification
        pipeline as typed text, so there is exactly one verdict system.

        Raises:
            ServiceUnavailableError: no API key configured.
            RateLimitError: Gemini quota or rate limit reached.
            ServiceError: Gemini failed, or could not read the image.
        """
        client = self.client

        config = self._build_config(
            SCREENSHOT_EXTRACTION_SYSTEM_PROMPT, GeminiScreenshotPayload
        )
        contents = [
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            SCREENSHOT_USER_PROMPT,
        ]

        response = await self._generate_with_retry(client, contents, config)
        payload = self._extract_payload(response, GeminiScreenshotPayload)

        try:
            extraction = ScreenshotExtraction.from_payload(payload)
        except ValidationError as exc:
            logger.error("screenshot extraction failed strict validation: %s", exc)
            raise ServiceError(
                "The image could not be read properly. Please try another screenshot."
            ) from exc

        logger.info(
            "screenshot read: kind=%s lang=%s claim=%s chars=%d date=%s source=%s",
            extraction.kind.value,
            extraction.language.value,
            extraction.has_factual_claim,
            len(extraction.extracted_text),
            extraction.visible_date or "-",
            extraction.visible_source or "-",
        )
        return extraction

    async def _generate_with_retry(
        self,
        client: genai.Client,
        contents: str | list[object],
        config: types.GenerateContentConfig,
    ) -> object:
        """Call Gemini, retrying only errors that a retry can actually fix.

        Flash models routinely answer 503 "high demand" under load, which resolves
        on its own. A 4xx (bad key, bad request, exhausted quota) will return the
        same answer every time, so retrying it only delays the error the user needs
        to see.
        """
        attempts = self._settings.gemini_max_retries + 1
        last_error: genai_errors.ServerError | None = None

        for attempt in range(1, attempts + 1):
            try:
                return await client.aio.models.generate_content(
                    model=self._settings.gemini_model,
                    contents=contents,
                    config=config,
                )
            except genai_errors.ClientError as exc:
                if getattr(exc, "code", None) == 429:
                    # Free-tier Gemini allows only a handful of requests per minute.
                    # The wait is far longer than a web request should block for, so
                    # report it honestly instead of retrying.
                    logger.warning("Gemini rate limit hit: %s", exc)
                    raise RateLimitError(
                        "The AI service rate limit was reached. Please wait a moment "
                        "and try again."
                    ) from exc
                logger.error("Gemini rejected the claim analysis request: %s", exc)
                raise ServiceError(
                    "The AI service rejected the request. Check the Gemini API key and quota.",
                    details={"provider_status": getattr(exc, "code", None)},
                ) from exc
            except genai_errors.ServerError as exc:
                last_error = exc
                logger.warning(
                    "Gemini server error (attempt %d/%d): %s", attempt, attempts, exc
                )
                if attempt < attempts:
                    await asyncio.sleep(
                        self._settings.gemini_retry_backoff_seconds * attempt
                    )
                    continue
            except genai_errors.APIError as exc:
                logger.error("Gemini API error during claim analysis: %s", exc)
                raise ServiceError("The AI service could not analyse this claim.") from exc
            except ShottiError:
                # Already a well-formed application error; never re-wrap it into a
                # vaguer one, or the caller loses the actionable message and status.
                raise
            except Exception as exc:  # network failure, timeout, SDK surprise
                logger.exception("Unexpected failure calling Gemini: %s", exc)
                raise ServiceError(
                    "Could not reach the AI service. Please try again."
                ) from exc

        logger.error("Gemini unavailable after %d attempts", attempts)
        raise ServiceError(
            "The AI service is busy right now. Please try again in a moment."
        ) from last_error

    def _build_config(
        self,
        system_instruction: str,
        schema: type[PayloadT],
    ) -> types.GenerateContentConfig:
        """Shared generation config for every structured-output call."""
        return types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=schema,
            # Fact-checking should be reproducible, not creative.
            temperature=0.0,
            # These stages call no tools; AFC is on by default and the SDK warns
            # about using it here, so turn it off explicitly.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            http_options=types.HttpOptions(timeout=self._settings.gemini_timeout_ms),
        )

    @staticmethod
    def _extract_payload(response: object, schema: type[PayloadT]) -> PayloadT:
        """Pull the parsed object out of a Gemini response.

        The SDK populates ``.parsed`` when a response_schema is set, but that can be
        None if the model was cut off or returned prose, so fall back to parsing
        ``.text`` before giving up.
        """
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, schema):
            return parsed

        if isinstance(parsed, dict):
            try:
                return schema.model_validate(parsed)
            except ValidationError as exc:
                raise ServiceError(
                    "The AI service returned an unexpected response format."
                ) from exc

        text = (getattr(response, "text", None) or "").strip()
        if not text:
            raise ServiceError(
                "The AI service returned an empty response. Please try again."
            )
        try:
            return schema.model_validate_json(text)
        except ValidationError as exc:
            logger.error("Could not parse Gemini response: %s", text[:500])
            raise ServiceError(
                "The AI service returned an unexpected response format."
            ) from exc


def get_gemini_service(settings: Settings) -> GeminiService:
    """Factory used by routers via Depends, and by tests with a stub Settings."""
    return GeminiService(settings)
