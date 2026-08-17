"""Schemas for screenshot claim extraction.

Same two-layer split as the other Gemini stages: a plain wire schema, and a strict
internal model.

This stage reads an image and reports what it says. It does not judge the claim, and
it does not verify anything about the screenshot's authenticity — a screenshot can be
edited, and we have no way to detect that, so nothing here should imply otherwise.
"""

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from app.models.claim import DetectedLanguage
from app.utils.text import truncate_text

MAX_EXTRACTED_TEXT_CHARS = 4_000
MAX_CLAIM_CHARS = 1_000


class ScreenshotKind(StrEnum):
    """What sort of image this appears to be."""

    SOCIAL_POST = "social_post"
    NEWS_ARTICLE = "news_article"
    NEWS_CARD = "news_card"
    MESSAGING = "messaging"
    VIDEO_FRAME = "video_frame"
    DOCUMENT = "document"
    OTHER = "other"


class GeminiScreenshotPayload(BaseModel):
    """Flat structure Gemini fills when reading a screenshot."""

    extracted_text: str = Field(
        description=(
            "All readable text in the image, transcribed verbatim in its original "
            "language and script. Preserve the original wording exactly."
        )
    )
    primary_claim: str = Field(
        description=(
            "The single central factual assertion the image is making, as one clear "
            "sentence in the language of the image. Empty string if there is no "
            "factual claim."
        )
    )
    language: DetectedLanguage = Field(description="Language of the text in the image.")
    kind: ScreenshotKind = Field(description="What sort of image this is.")
    visible_date: str | None = Field(
        default=None,
        description=(
            "Any date or timestamp visible in the image, copied as shown "
            "(e.g. '১৬ আগস্ট ২০২৬', '3 hours ago'). Null if none is visible."
        ),
    )
    visible_source: str | None = Field(
        default=None,
        description=(
            "The publisher, page name, or account handle visible in the image "
            "(e.g. 'Prothom Alo', '@somebody'). Null if none is visible."
        ),
    )
    has_factual_claim: bool = Field(
        description=(
            "False when the image contains no checkable factual assertion — a meme, "
            "an opinion, a selfie, or unreadable text."
        )
    )
    notes: str | None = Field(
        default=None,
        description=(
            "One short sentence on anything that affects reading the image: text cut "
            "off, low quality, or a claim quoted from someone else."
        ),
    )


class ScreenshotExtraction(BaseModel):
    """Validated reading of a screenshot, shown to the user before verification."""

    extracted_text: str = Field(description="Verbatim transcription of the image text.")
    primary_claim: str = Field(description="The claim to verify. Empty if none was found.")
    language: DetectedLanguage
    kind: ScreenshotKind
    visible_date: str | None = None
    visible_source: str | None = None
    has_factual_claim: bool
    notes: str | None = None

    @field_validator("extracted_text")
    @classmethod
    def _cap_text(cls, value: str) -> str:
        return truncate_text(value.strip(), MAX_EXTRACTED_TEXT_CHARS)

    @field_validator("primary_claim")
    @classmethod
    def _cap_claim(cls, value: str) -> str:
        return truncate_text(value.strip(), MAX_CLAIM_CHARS)

    @classmethod
    def from_payload(cls, payload: GeminiScreenshotPayload) -> "ScreenshotExtraction":
        claim = payload.primary_claim.strip()
        return cls(
            extracted_text=payload.extracted_text,
            primary_claim=claim,
            language=payload.language,
            kind=payload.kind,
            visible_date=(payload.visible_date or "").strip() or None,
            visible_source=(payload.visible_source or "").strip() or None,
            # A claim flag with no claim text behind it is not a claim.
            has_factual_claim=payload.has_factual_claim and bool(claim),
            notes=(payload.notes or "").strip() or None,
        )
