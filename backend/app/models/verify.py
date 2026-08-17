"""Request/response schemas for the claim verification endpoint."""

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from app.models.evidence import EvidenceItem, Source, SourceAssessment
from app.models.screenshot import ScreenshotExtraction

MAX_CLAIM_LENGTH = 1000


class Verdict(StrEnum):
    """The four possible outcomes of a verification."""

    LIKELY_TRUE = "LIKELY_TRUE"
    LIKELY_FALSE = "LIKELY_FALSE"
    UNVERIFIED = "UNVERIFIED"
    MISLEADING = "MISLEADING"


class Language(StrEnum):
    """Claim language. `AUTO` asks the backend to detect it."""

    AUTO = "auto"
    BANGLA = "bn"
    ENGLISH = "en"


class VerifyRequest(BaseModel):
    """A factual claim submitted for verification."""

    claim: str = Field(
        min_length=3,
        max_length=MAX_CLAIM_LENGTH,
        description="The factual claim to verify, in Bangla or English.",
    )
    language: Language = Field(
        default=Language.AUTO, description="Claim language; detected when 'auto'."
    )

    @field_validator("claim")
    @classmethod
    def _strip_and_require_content(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 3:
            raise ValueError("Claim must contain at least 3 non-whitespace characters.")
        return stripped


class VerifyMeta(BaseModel):
    """Diagnostics about how the verification ran.

    Kept out of the main body so the frontend can render a result without reading
    it, but present so a partial result is never passed off as a complete one.
    """

    duration_ms: int = Field(ge=0, description="Total server-side processing time.")
    sources_found: int = Field(
        default=0, ge=0, description="Search hits before de-duplication and ranking."
    )
    sources_used: int = Field(
        default=0, ge=0, description="Sources successfully scraped and analysed."
    )
    queries_used: int = Field(default=0, ge=0, description="Search queries that succeeded.")
    dropped_evidence_count: int = Field(
        default=0,
        ge=0,
        description="Quotes discarded because they were not found in the cited source.",
    )
    has_conflicting_evidence: bool = False
    relies_on_speculation: bool = False
    degraded: bool = Field(
        default=False,
        description="True when a stage failed or was skipped, so the result is partial.",
    )


class VerifyResponse(BaseModel):
    """The full verification result rendered by the frontend.

    Contains no raw model output: every field has been through strict validation,
    and every source is one Firecrawl actually retrieved.
    """

    claim: str = Field(description="The claim exactly as the user submitted it.")
    normalized_claim: str = Field(
        description="Atomic, English restatement of the claim used for research."
    )
    verdict: Verdict
    confidence_score: float = Field(
        ge=0.0, le=1.0, description="Strength of the evidence behind the verdict, 0–1."
    )
    explanation: str = Field(
        description="Two or three sentences, in the language of the original claim."
    )
    supporting_evidence: list[EvidenceItem] = Field(default_factory=list)
    contradicting_evidence: list[EvidenceItem] = Field(default_factory=list)
    important_context: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)

    # --- additions beyond the core contract -------------------------------
    claim_id: str = Field(description="Identifier for this result, used by the chat endpoint.")
    language: str = Field(description="Language detected in the claim: bn, en, mixed, or other.")
    source_assessments: list[SourceAssessment] = Field(
        default_factory=list,
        description="Per-source stance, reliability, and outdatedness.",
    )
    meta: VerifyMeta


class ScreenshotVerifyResponse(VerifyResponse):
    """A screenshot verification: the same verdict contract, plus what was read.

    Subclassing rather than duplicating is deliberate — screenshots must not get a
    second verdict system. ``claim`` holds the extracted claim that was verified, so
    the frontend can render this with the same component as a typed claim.
    """

    extraction: ScreenshotExtraction = Field(
        description="What was read from the image, shown to the user for confirmation."
    )


class ScreenshotExtractionResponse(BaseModel):
    """Extraction only, for the confirm-before-verify step.

    Reading an image is one cheap Gemini call; verifying is two calls plus web
    research. Letting the user correct a misread claim before that spend is both
    kinder and cheaper than verifying the wrong sentence confidently.
    """

    extraction: ScreenshotExtraction
    suggested_claim: str = Field(
        description="Pre-filled claim for the input box. Empty when none was found."
    )


class HealthResponse(BaseModel):
    """Liveness plus which integrations are configured."""

    status: str = Field(description="'ok' when the app is serving requests.")
    app: str
    version: str
    services: dict[str, bool] = Field(
        description="Per-integration credential presence. Booleans only, never keys."
    )
