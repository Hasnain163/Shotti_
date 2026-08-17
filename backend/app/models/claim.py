"""Schemas for the claim analysis stage.

Two layers on purpose:

* ``GeminiClaimPayload`` is the *wire* schema handed to Gemini as its structured
  output schema. It stays deliberately plain — Gemini's schema converter ignores
  or rejects many Pydantic constraints (bounds, custom validators), so encoding
  our rules there would give a false sense of safety.
* ``ClaimAnalysis`` is the *strict* internal model. Everything the pipeline and
  the API touch goes through it, where bounds and normalisation are enforced for
  real. ``ClaimAnalysis.from_payload`` is the only bridge between the two.
"""

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

MAX_ENTITIES = 12
MAX_QUESTIONS = 6
MAX_QUERIES = 5
MAX_TEMPORAL_REFERENCES = 6


class DetectedLanguage(StrEnum):
    """Language Gemini detected in the claim.

    Distinct from ``models.verify.Language``, which is the *requested* language
    and can be ``auto``. This enum is an observation, so it has no ``auto``.
    """

    BANGLA = "bn"
    ENGLISH = "en"
    MIXED = "mixed"
    OTHER = "other"


class ClaimTopic(StrEnum):
    """Coarse subject area, used for prompt routing and source weighting later."""

    POLITICS = "politics"
    HEALTH = "health"
    SCIENCE = "science"
    ECONOMY = "economy"
    TECHNOLOGY = "technology"
    SPORTS = "sports"
    RELIGION = "religion"
    CRIME = "crime"
    ENVIRONMENT = "environment"
    ENTERTAINMENT = "entertainment"
    SOCIETY = "society"
    OTHER = "other"


class GeminiClaimPayload(BaseModel):
    """Flat structure Gemini is asked to fill. Descriptions double as prompt text."""

    normalized_claim: str = Field(
        description="One atomic, self-contained English restatement of the claim."
    )
    language: DetectedLanguage = Field(description="Language of the original claim.")
    topic: ClaimTopic = Field(description="Coarse subject area of the claim.")
    entities: list[str] = Field(
        default_factory=list,
        description="People, organisations, places, and numbers named in the claim.",
    )
    temporal_references: list[str] = Field(
        default_factory=list,
        description="Time expressions exactly as written in the claim, e.g. 'গতকাল', 'last year'.",
    )
    resolved_timeframe: str | None = Field(
        default=None,
        description=(
            "The time window the claim refers to, resolved to absolute terms using "
            "today's date, e.g. '2026-08-16' or 'around 2024'. Null if the claim is timeless."
        ),
    )
    factual_proposition: str = Field(
        description=(
            "The single check-worthy assertion, stated so it can be confirmed or "
            "refuted by evidence. No hedging, no verdict."
        )
    )
    verification_questions: list[str] = Field(
        default_factory=list,
        description="Specific questions a fact-checker must answer to settle the claim.",
    )
    search_queries: list[str] = Field(
        default_factory=list,
        description=(
            "Web search queries. Mix Bangla and English when the claim is about "
            "Bangladesh so local outlets are reachable."
        ),
    )
    is_checkable: bool = Field(
        description=(
            "False when the text is an opinion, prediction, question, or gibberish "
            "rather than a verifiable factual claim."
        )
    )
    uncheckable_reason: str | None = Field(
        default=None,
        description="If is_checkable is false, one short sentence explaining why.",
    )


def _clean_list(values: list[str], limit: int) -> list[str]:
    """Strip, drop blanks, de-duplicate case-insensitively, and cap the length."""
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        item = value.strip()
        key = item.lower()
        if not item or key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    return cleaned[:limit]


class ClaimAnalysis(BaseModel):
    """Validated understanding of a claim — the investigation plan.

    Deliberately carries no verdict, confidence, or evidence. Judging the claim
    is a later stage's job; mixing the two here is what makes fact-checkers
    reason backwards from a guess.
    """

    original_claim: str = Field(description="The claim exactly as the user submitted it.")
    normalized_claim: str = Field(min_length=1)
    language: DetectedLanguage
    topic: ClaimTopic
    entities: list[str] = Field(default_factory=list, max_length=MAX_ENTITIES)
    temporal_references: list[str] = Field(
        default_factory=list, max_length=MAX_TEMPORAL_REFERENCES
    )
    resolved_timeframe: str | None = None
    factual_proposition: str = Field(min_length=1)
    verification_questions: list[str] = Field(default_factory=list, max_length=MAX_QUESTIONS)
    search_queries: list[str] = Field(default_factory=list, max_length=MAX_QUERIES)
    is_checkable: bool
    uncheckable_reason: str | None = None

    @field_validator("normalized_claim", "factual_proposition")
    @classmethod
    def _require_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Gemini returned an empty value for a required field.")
        return stripped

    @classmethod
    def from_payload(cls, payload: GeminiClaimPayload, original_claim: str) -> "ClaimAnalysis":
        """Normalise a raw Gemini payload into the strict internal model."""
        return cls(
            original_claim=original_claim,
            normalized_claim=payload.normalized_claim,
            language=payload.language,
            topic=payload.topic,
            entities=_clean_list(payload.entities, MAX_ENTITIES),
            temporal_references=_clean_list(payload.temporal_references, MAX_TEMPORAL_REFERENCES),
            resolved_timeframe=(payload.resolved_timeframe or "").strip() or None,
            factual_proposition=payload.factual_proposition,
            verification_questions=_clean_list(payload.verification_questions, MAX_QUESTIONS),
            search_queries=_clean_list(payload.search_queries, MAX_QUERIES),
            is_checkable=payload.is_checkable,
            uncheckable_reason=(payload.uncheckable_reason or "").strip() or None,
        )
