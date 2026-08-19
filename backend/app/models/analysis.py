"""Schemas for the evidence analysis stage — the stage that produces the verdict.

Same two-layer split as the claim stage: a plain wire schema for Gemini, and a
strict internal model that enforces the rules for real.

The rule that matters most here is grounding. Gemini is never asked for a URL,
only for an integer index into the sources Firecrawl actually retrieved, so an
invented source cannot be represented. Quotes are then checked against the real
scraped text, and anything that does not appear there is discarded.
"""

import logging

from pydantic import BaseModel, Field, field_validator

# Stance, Reliability, and SourceAssessment live in models.evidence so the API layer
# can use them too; they are re-exported here since this is where they are produced.
from app.models.evidence import (
    EvidenceItem,
    Reliability,
    SourceAssessment,
    Stance,
)
from app.models.source import ResearchSource
from app.models.verify import Verdict
from app.utils.text import quote_is_grounded, truncate_text

__all__ = [
    "EvidenceAnalysis",
    "GeminiEvidenceItem",
    "GeminiSourceAssessment",
    "GeminiVerdictPayload",
    "Reliability",
    "SourceAssessment",
    "Stance",
]

logger = logging.getLogger(__name__)

MAX_EVIDENCE_ITEMS = 6
MAX_CONTEXT_NOTES = 4
MAX_QUOTE_CHARS = 500
MAX_EXPLANATION_CHARS = 800
# Evidence gathered from a few web pages never justifies certainty.
MAX_REPORTABLE_CONFIDENCE = 0.95


class GeminiEvidenceItem(BaseModel):
    """One quote Gemini attributes to a numbered source."""

    source_index: int = Field(
        description="Index of the source this quote came from, as numbered in the prompt."
    )
    quote: str = Field(
        description=(
            "Text copied verbatim from that source. Never paraphrase, never write a "
            "sentence the source does not contain."
        )
    )


class GeminiSourceAssessment(BaseModel):
    """Gemini's read on one source."""

    source_index: int = Field(description="Index of the source being assessed.")
    stance: Stance = Field(description="Whether this source supports, contradicts, or is neutral.")
    reliability: Reliability = Field(
        description="How much weight this source deserves, given the publisher and specificity."
    )
    is_outdated: bool = Field(
        description=(
            "True when this source is too old to settle the claim, or has been "
            "superseded by later reporting."
        )
    )
    note: str = Field(
        description="One short sentence explaining the stance and reliability call."
    )


class GeminiVerdictPayload(BaseModel):
    """Flat structure Gemini is asked to fill for the verdict."""

    verdict: Verdict = Field(description="Exactly one of the four allowed verdicts.")
    confidence_score: float = Field(
        description="0.0 to 1.0. How confident the verdict is, given this evidence only."
    )
    short_explanation: str = Field(
        description=(
            "Two or three sentences, in the same language as the original claim, "
            "explaining the verdict by reference to the evidence."
        )
    )
    supporting_evidence: list[GeminiEvidenceItem] = Field(
        default_factory=list, description="Verbatim quotes that support the claim."
    )
    contradicting_evidence: list[GeminiEvidenceItem] = Field(
        default_factory=list, description="Verbatim quotes that contradict the claim."
    )
    important_context: list[str] = Field(
        default_factory=list,
        description=(
            "Caveats a reader needs: outdated sources, conflicting reports, missing "
            "dates, or a detail that changes how the claim should be read."
        ),
    )
    source_assessments: list[GeminiSourceAssessment] = Field(
        default_factory=list, description="One assessment per source provided, in order."
    )
    has_conflicting_evidence: bool = Field(
        description="True when credible sources disagree with each other."
    )
    relies_on_speculation: bool = Field(
        description=(
            "True when the sources offer opinion, prediction, or rumour rather than "
            "documented fact."
        )
    )


class EvidenceAnalysis(BaseModel):
    """The verdict, with every claim about the evidence checked against it."""

    verdict: Verdict
    confidence_score: float = Field(ge=0.0, le=1.0)
    short_explanation: str = Field(min_length=1)
    supporting_evidence: list[EvidenceItem] = Field(default_factory=list)
    contradicting_evidence: list[EvidenceItem] = Field(default_factory=list)
    important_context: list[str] = Field(default_factory=list, max_length=MAX_CONTEXT_NOTES)
    source_assessments: list[SourceAssessment] = Field(default_factory=list)
    has_conflicting_evidence: bool = False
    relies_on_speculation: bool = False
    dropped_evidence_count: int = Field(
        default=0,
        description=(
            "Quotes discarded because they did not appear in the cited source. "
            "Above zero means the model was reaching."
        ),
    )

    @field_validator("short_explanation")
    @classmethod
    def _require_explanation(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("The analysis must explain its verdict.")
        return truncate_text(stripped, MAX_EXPLANATION_CHARS)

    @classmethod
    def from_payload(
        cls,
        payload: GeminiVerdictPayload,
        sources: list[ResearchSource],
    ) -> "EvidenceAnalysis":
        """Validate a raw payload against the sources that were actually retrieved.

        Three things happen here, in order:

        1. Evidence quotes are checked against the real scraped text and dropped if
           they are not there.
        2. Assessments are matched to real sources; unknown indices are discarded and
           the URL is filled in from our own record, never from the model.
        3. The verdict is reconciled with the evidence that survived, so a confident
           claim cannot rest on quotes that were just thrown away.
        """
        supporting, dropped_support = _ground_evidence(
            payload.supporting_evidence, sources, "supporting"
        )
        contradicting, dropped_contra = _ground_evidence(
            payload.contradicting_evidence, sources, "contradicting"
        )
        assessments = _validate_assessments(payload.source_assessments, sources)

        verdict, confidence, context = _reconcile_verdict(
            verdict=payload.verdict,
            confidence=payload.confidence_score,
            supporting=supporting,
            contradicting=contradicting,
            sources=sources,
            context=[note.strip() for note in payload.important_context if note.strip()],
        )

        return cls(
            verdict=verdict,
            confidence_score=confidence,
            short_explanation=payload.short_explanation,
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            important_context=context[:MAX_CONTEXT_NOTES],
            source_assessments=assessments,
            has_conflicting_evidence=payload.has_conflicting_evidence,
            relies_on_speculation=payload.relies_on_speculation,
            dropped_evidence_count=dropped_support + dropped_contra,
        )

    @classmethod
    def unverified(cls, explanation: str, context: list[str] | None = None) -> "EvidenceAnalysis":
        """A verdict of last resort, used when there is nothing to analyse.

        No evidence means no verdict, and zero confidence — not a coin flip.
        """
        return cls(
            verdict=Verdict.UNVERIFIED,
            confidence_score=0.0,
            short_explanation=explanation,
            important_context=context or [],
        )


def _ground_evidence(
    items: list[GeminiEvidenceItem],
    sources: list[ResearchSource],
    label: str,
) -> tuple[list[EvidenceItem], int]:
    """Keep only quotes that really appear in the source they are attributed to."""
    kept: list[EvidenceItem] = []
    dropped = 0
    seen: set[tuple[int, str]] = set()

    for item in items:
        quote = item.quote.strip()
        if not quote:
            continue

        if not 0 <= item.source_index < len(sources):
            logger.warning(
                "dropped %s quote citing source %d; only %d sources exist",
                label,
                item.source_index,
                len(sources),
            )
            dropped += 1
            continue

        source = sources[item.source_index]
        if not quote_is_grounded(quote, source.content):
            logger.warning(
                "dropped ungrounded %s quote attributed to %s", label, source.domain
            )
            dropped += 1
            continue

        key = (item.source_index, quote.casefold())
        if key in seen:
            continue
        seen.add(key)

        kept.append(
            EvidenceItem(quote=truncate_text(quote, MAX_QUOTE_CHARS), source_index=item.source_index)
        )
        if len(kept) >= MAX_EVIDENCE_ITEMS:
            break

    return kept, dropped


def _validate_assessments(
    assessments: list[GeminiSourceAssessment],
    sources: list[ResearchSource],
) -> list[SourceAssessment]:
    """Attach assessments to real sources, filling URLs from our own records."""
    validated: list[SourceAssessment] = []
    seen: set[int] = set()

    for assessment in assessments:
        if not 0 <= assessment.source_index < len(sources):
            logger.warning(
                "dropped assessment for unknown source index %d", assessment.source_index
            )
            continue
        if assessment.source_index in seen:
            continue
        seen.add(assessment.source_index)

        source = sources[assessment.source_index]
        validated.append(
            SourceAssessment(
                source_index=assessment.source_index,
                url=source.url,
                domain=source.domain,
                stance=assessment.stance,
                reliability=assessment.reliability,
                is_outdated=assessment.is_outdated,
                published_date=source.published_date,
                note=truncate_text(assessment.note.strip(), 300),
            )
        )

    if len(validated) < len(sources):
        logger.info(
            "model assessed %d of %d sources", len(validated), len(sources)
        )
    return sorted(validated, key=lambda item: item.source_index)


def _reconcile_verdict(
    verdict: Verdict,
    confidence: float,
    supporting: list[EvidenceItem],
    contradicting: list[EvidenceItem],
    sources: list[ResearchSource],
    context: list[str],
) -> tuple[Verdict, float, list[str]]:
    """Keep the verdict honest about the evidence that actually survived.

    A verdict is a claim about evidence, so it cannot outlive the quotes that
    justified it. If grounding threw away everything that supported a LIKELY_TRUE,
    reporting it unchanged would present the model's memory as research.
    """
    confidence = min(max(confidence, 0.0), 1.0)
    notes = list(context)

    if not sources:
        return Verdict.UNVERIFIED, 0.0, notes

    if verdict is Verdict.LIKELY_TRUE and not supporting:
        logger.warning("downgrading LIKELY_TRUE with no grounded supporting evidence")
        notes.append(
            "No quote supporting this claim could be traced back to the sources, so "
            "the claim is reported as unverified rather than true."
        )
        return Verdict.UNVERIFIED, min(confidence, 0.3), notes

    if verdict is Verdict.LIKELY_FALSE and not contradicting:
        logger.warning("downgrading LIKELY_FALSE with no grounded contradicting evidence")
        notes.append(
            "No quote contradicting this claim could be traced back to the sources, so "
            "the claim is reported as unverified rather than false."
        )
        return Verdict.UNVERIFIED, min(confidence, 0.3), notes

    if not supporting and not contradicting:
        if verdict is not Verdict.UNVERIFIED:
            logger.warning("downgrading %s with no grounded evidence at all", verdict)
            notes.append("The sources retrieved did not directly address this claim.")
            verdict = Verdict.UNVERIFIED
        # An already-unverified verdict lands here too, and it must lose its
        # confidence as well: nothing traceable is behind it, so a high score would
        # render as "Unverified — strong evidence", which contradicts itself.
        return verdict, min(confidence, 0.3), notes

    # A confident verdict on a single source overstates what one page can settle.
    if confidence > 0.8 and len(sources) < 2:
        confidence = 0.8

    # Never report certainty. A handful of scraped pages cannot put a claim beyond
    # doubt, and a displayed 100% invites the reader to stop thinking.
    return verdict, min(confidence, MAX_REPORTABLE_CONFIDENCE), notes
