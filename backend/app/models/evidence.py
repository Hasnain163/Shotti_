"""Evidence and source schemas shared by the verify and chat responses.

These live here, rather than beside the analysis logic, because both the analysis
stage and the API response layer need them — and the analysis module already imports
Verdict from the verify module, so importing the other way would be circular.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class Source(BaseModel):
    """A web page that was searched, scraped, and used as evidence."""

    title: str = Field(description="Page title, or the URL if no title was found.")
    url: str = Field(description="Canonical URL of the source.")
    domain: str = Field(description="Host of the URL, shown as a credibility hint.")
    snippet: str | None = Field(
        default=None, description="Short excerpt giving the reader context."
    )
    published_date: str | None = Field(
        default=None,
        description="Publication date if the page exposed one. Often unavailable.",
    )
    source_type: str | None = Field(
        default=None,
        description="Publisher category, e.g. 'news', 'fact_check', 'government'.",
    )


class EvidenceItem(BaseModel):
    """A verbatim quote from one numbered source, for or against the claim."""

    quote: str = Field(description="Verbatim excerpt from the source — never paraphrased.")
    source_index: int = Field(
        ge=0, description="Index into the response's `sources` list."
    )


class Stance(StrEnum):
    """What a single source does to the claim."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"


class Reliability(StrEnum):
    """How much weight a source's testimony deserves."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SourceAssessment(BaseModel):
    """A validated per-source assessment.

    ``url`` is always copied from the source we retrieved, never from model output.
    """

    source_index: int = Field(ge=0)
    url: str
    domain: str
    stance: Stance
    reliability: Reliability
    is_outdated: bool = False
    published_date: str | None = None
    note: str = ""
