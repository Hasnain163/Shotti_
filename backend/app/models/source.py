"""Normalised research sources produced by the Firecrawl research agent."""

from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.evidence import Source


class SourceType(StrEnum):
    """What kind of publisher a source is.

    Used to weight evidence later — a government statistics page and a personal
    blog should not carry the same weight when Gemini judges the claim.
    """

    FACT_CHECK = "fact_check"
    NEWS = "news"
    GOVERNMENT = "government"
    ACADEMIC = "academic"
    ENCYCLOPEDIA = "encyclopedia"
    SOCIAL = "social"
    BLOG = "blog"
    OTHER = "other"


class SearchCandidate(BaseModel):
    """A search hit, before we have tried to fetch its content."""

    url: str
    title: str = ""
    snippet: str = ""
    published_date: str | None = None
    source_type: SourceType = SourceType.OTHER
    domain: str = ""
    found_by_query: str = ""
    # Higher scores are scraped first. Derived from publisher reputation.
    credibility: int = 0


class ResearchSource(BaseModel):
    """A source that was successfully fetched and cleaned.

    This is the internal shape the evidence-analysis stage will consume. It is
    deliberately richer than the API-facing ``Source``.
    """

    title: str
    url: str
    domain: str
    published_date: str | None = Field(
        default=None,
        description="Publication date if the page exposed one; often missing.",
    )
    content: str = Field(description="Cleaned, length-capped page text.")
    source_type: SourceType
    snippet: str = ""
    found_by_query: str = ""
    credibility: int = 0

    def to_api_source(self) -> Source:
        """Project down to the public shape returned by /api/verify."""
        return Source(
            title=self.title,
            url=self.url,
            domain=self.domain,
            snippet=self.snippet or None,
            published_date=self.published_date,
            source_type=self.source_type.value,
        )


class FailedSource(BaseModel):
    """A candidate we could not use, kept so failures are visible not silent."""

    url: str
    domain: str = ""
    reason: str


class ResearchBundle(BaseModel):
    """Everything the research stage found for one claim."""

    sources: list[ResearchSource] = Field(default_factory=list)
    failures: list[FailedSource] = Field(default_factory=list)
    queries_used: list[str] = Field(default_factory=list)
    queries_failed: list[str] = Field(default_factory=list)
    candidates_found: int = 0
    total_content_chars: int = 0
    degraded: bool = Field(
        default=False,
        description="True when any query or scrape failed, so the evidence is partial.",
    )

    @property
    def has_evidence(self) -> bool:
        return bool(self.sources)
