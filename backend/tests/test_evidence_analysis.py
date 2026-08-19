"""Tests for the Gemini evidence analysis agent.

Fully mocked — no network, no GEMINI_API_KEY. The point of most of these tests is
not that the agent relays what the model said, but that it refuses to relay claims
the retrieved sources do not actually contain.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.config import Settings
from app.models.analysis import (
    EvidenceAnalysis,
    GeminiVerdictPayload,
    Reliability,
    Stance,
)
from app.models.claim import ClaimAnalysis, ClaimTopic, DetectedLanguage
from app.models.source import ResearchSource, SourceType
from app.models.verify import Verdict
from app.services.gemini import GeminiService

TARGET = "google.genai.models.AsyncModels.generate_content"

SOURCE_0_TEXT = (
    "Pakistan defeated India by 180 runs in the final of the 2017 ICC Champions "
    "Trophy at The Oval in London on 18 June 2017. It was Pakistan's first "
    "Champions Trophy title. Bangladesh reached the semi-final stage and were "
    "eliminated by India."
)
SOURCE_1_TEXT = (
    "The Bangladesh Meteorological Department recorded a magnitude 5.2 earthquake "
    "near Dhaka on 16 August 2026. No casualties were reported. Officials said the "
    "tremor lasted around eight seconds and was felt in several districts."
)


@pytest_asyncio.fixture(autouse=True)
async def close_gemini_clients():
    """Close SDK clients created during a test. See test_gemini.py for why."""
    created: list[GeminiService] = []
    original_init = GeminiService.__init__

    def tracking_init(self, settings):
        original_init(self, settings)
        created.append(self)

    with patch.object(GeminiService, "__init__", tracking_init):
        yield

    for service in created:
        await service.aclose()


def make_settings(**overrides) -> Settings:
    defaults = {
        "gemini_api_key": "test-key-not-real",
        "gemini_model": "gemini-3.7-flash",
        "gemini_retry_backoff_seconds": 0.0,
        "firecrawl_api_key": None,
        "elevenlabs_api_key": None,
    }
    return Settings(**{**defaults, **overrides})


def make_claim_analysis(**overrides) -> ClaimAnalysis:
    defaults = {
        "original_claim": "Bangladesh won the ICC Champions Trophy in 2017.",
        "normalized_claim": "Bangladesh won the 2017 ICC Champions Trophy.",
        "language": DetectedLanguage.ENGLISH,
        "topic": ClaimTopic.SPORTS,
        "entities": ["Bangladesh", "ICC Champions Trophy"],
        "temporal_references": ["2017"],
        "resolved_timeframe": "2017",
        "factual_proposition": "Bangladesh won the 2017 ICC Champions Trophy.",
        "verification_questions": ["Which team won the 2017 ICC Champions Trophy?"],
        "search_queries": ["2017 Champions Trophy winner"],
        "is_checkable": True,
    }
    return ClaimAnalysis(**{**defaults, **overrides})


def make_source(index: int = 0, **overrides) -> ResearchSource:
    presets = {
        0: {
            "title": "2017 Champions Trophy",
            "url": "https://en.wikipedia.org/wiki/2017_Champions_Trophy",
            "domain": "en.wikipedia.org",
            "content": SOURCE_0_TEXT,
            "source_type": SourceType.ENCYCLOPEDIA,
            "published_date": None,
            "credibility": 80,
        },
        1: {
            "title": "Earthquake near Dhaka",
            "url": "https://www.thedailystar.net/quake",
            "domain": "thedailystar.net",
            "content": SOURCE_1_TEXT,
            "source_type": SourceType.NEWS,
            "published_date": "2026-08-16",
            "credibility": 75,
        },
    }
    return ResearchSource(**{**presets[index], **overrides})


def make_payload(**overrides) -> GeminiVerdictPayload:
    defaults = {
        "verdict": "LIKELY_FALSE",
        "confidence_score": 0.9,
        "short_explanation": "Pakistan won the 2017 Champions Trophy, not Bangladesh.",
        "supporting_evidence": [],
        "contradicting_evidence": [
            {
                "source_index": 0,
                "quote": "Pakistan defeated India by 180 runs in the final of the 2017 ICC Champions Trophy",
            }
        ],
        "important_context": ["Bangladesh reached the semi-final but did not win."],
        "source_assessments": [
            {
                "source_index": 0,
                "stance": "contradicts",
                "reliability": "medium",
                "is_outdated": False,
                "note": "Directly states the tournament winner.",
            }
        ],
        "has_conflicting_evidence": False,
        "relies_on_speculation": False,
    }
    return GeminiVerdictPayload(**{**defaults, **overrides})


def stub_response(parsed=None, text: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(parsed=parsed, text=text)


async def analyze(service, payload, sources=None, claim_analysis=None, **kwargs):
    sources = sources if sources is not None else [make_source(0)]
    with patch(TARGET, AsyncMock(return_value=stub_response(parsed=payload))):
        return await service.analyze_evidence(
            claim_analysis or make_claim_analysis(), sources, **kwargs
        )


# --- happy path -------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_verdict_with_grounded_evidence() -> None:
    service = GeminiService(make_settings())
    result = await analyze(service, make_payload())

    assert isinstance(result, EvidenceAnalysis)
    assert result.verdict is Verdict.LIKELY_FALSE
    assert result.confidence_score == pytest.approx(0.8)  # capped: single source
    assert result.short_explanation
    assert len(result.contradicting_evidence) == 1
    assert result.contradicting_evidence[0].source_index == 0
    assert result.important_context
    assert result.dropped_evidence_count == 0


@pytest.mark.asyncio
async def test_verdict_is_always_one_of_the_four() -> None:
    service = GeminiService(make_settings())
    for verdict in ("LIKELY_TRUE", "LIKELY_FALSE", "UNVERIFIED", "MISLEADING"):
        payload = make_payload(
            verdict=verdict,
            supporting_evidence=[
                {"source_index": 0, "quote": "It was Pakistan's first Champions Trophy title."}
            ],
        )
        result = await analyze(service, payload)
        assert result.verdict.value in {
            "LIKELY_TRUE",
            "LIKELY_FALSE",
            "UNVERIFIED",
            "MISLEADING",
        }


@pytest.mark.asyncio
async def test_source_assessments_are_returned_per_source() -> None:
    service = GeminiService(make_settings())
    payload = make_payload(
        source_assessments=[
            {
                "source_index": 0,
                "stance": "contradicts",
                "reliability": "medium",
                "is_outdated": False,
                "note": "States the winner.",
            },
            {
                "source_index": 1,
                "stance": "neutral",
                "reliability": "high",
                "is_outdated": True,
                "note": "Unrelated to this claim.",
            },
        ]
    )

    result = await analyze(service, payload, sources=[make_source(0), make_source(1)])

    assert len(result.source_assessments) == 2
    first, second = result.source_assessments
    assert first.stance is Stance.CONTRADICTS
    assert first.reliability is Reliability.MEDIUM
    assert second.stance is Stance.NEUTRAL
    assert second.is_outdated is True
    # Dates and URLs come from our own records, never from the model.
    assert second.published_date == "2026-08-16"
    assert second.url == "https://www.thedailystar.net/quake"


@pytest.mark.asyncio
async def test_conflict_and_speculation_flags_are_carried_through() -> None:
    service = GeminiService(make_settings())
    payload = make_payload(has_conflicting_evidence=True, relies_on_speculation=True)

    result = await analyze(service, payload)

    assert result.has_conflicting_evidence is True
    assert result.relies_on_speculation is True


@pytest.mark.asyncio
async def test_prompt_carries_numbered_sources_dates_and_language() -> None:
    service = GeminiService(make_settings())
    mock = AsyncMock(return_value=stub_response(parsed=make_payload()))

    with patch(TARGET, mock):
        await service.analyze_evidence(
            make_claim_analysis(), [make_source(0), make_source(1)], today=date(2026, 8, 17)
        )

    contents = mock.await_args.kwargs["contents"]
    system = mock.await_args.kwargs["config"].system_instruction
    assert "--- SOURCE 0 ---" in contents and "--- SOURCE 1 ---" in contents
    assert "2026-08-17" in contents
    assert "published: 2026-08-16" in contents
    assert "UNKNOWN — no date available" in contents  # source 0 has no date
    assert "en.wikipedia.org" in contents
    assert mock.await_args.kwargs["config"].temperature == 0.0
    # The instructions the whole design depends on.
    assert "character-for-character" in system
    assert "Your own memory is not evidence" in system
    assert "MISLEADING" in system and "UNVERIFIED" in system


# --- grounding: the anti-fabrication guarantee -------------------------------


@pytest.mark.asyncio
async def test_invented_quote_is_dropped() -> None:
    """A quote the source does not contain must never reach the user."""
    service = GeminiService(make_settings())
    payload = make_payload(
        contradicting_evidence=[
            {
                "source_index": 0,
                "quote": "Bangladesh was disqualified from the tournament for cheating.",
            }
        ]
    )

    result = await analyze(service, payload)

    assert result.contradicting_evidence == []
    assert result.dropped_evidence_count == 1


@pytest.mark.asyncio
async def test_quote_attributed_to_the_wrong_source_is_dropped() -> None:
    service = GeminiService(make_settings())
    payload = make_payload(
        contradicting_evidence=[
            # Real text, but it belongs to source 1, not source 0.
            {"source_index": 0, "quote": "No casualties were reported."}
        ]
    )

    result = await analyze(service, payload, sources=[make_source(0), make_source(1)])

    assert result.contradicting_evidence == []
    assert result.dropped_evidence_count == 1


@pytest.mark.asyncio
async def test_out_of_range_source_index_is_dropped() -> None:
    """The model cannot cite a source that was never retrieved."""
    service = GeminiService(make_settings())
    payload = make_payload(
        contradicting_evidence=[{"source_index": 7, "quote": "Pakistan defeated India"}]
    )

    result = await analyze(service, payload)

    assert result.contradicting_evidence == []
    assert result.dropped_evidence_count == 1


@pytest.mark.asyncio
async def test_negative_source_index_is_dropped() -> None:
    service = GeminiService(make_settings())
    payload = make_payload(
        contradicting_evidence=[{"source_index": -1, "quote": "Pakistan defeated India"}]
    )

    result = await analyze(service, payload)

    assert result.dropped_evidence_count == 1


@pytest.mark.asyncio
async def test_assessment_for_unknown_source_is_dropped() -> None:
    service = GeminiService(make_settings())
    payload = make_payload(
        source_assessments=[
            {
                "source_index": 9,
                "stance": "supports",
                "reliability": "high",
                "is_outdated": False,
                "note": "Invented source.",
            }
        ]
    )

    result = await analyze(service, payload)

    assert result.source_assessments == []


@pytest.mark.asyncio
async def test_quote_differing_only_in_whitespace_and_case_is_kept() -> None:
    """Grounding must be strict about substance, not presentation."""
    service = GeminiService(make_settings())
    payload = make_payload(
        contradicting_evidence=[
            {
                "source_index": 0,
                "quote": "pakistan   defeated INDIA\n by 180 runs",
            }
        ]
    )

    result = await analyze(service, payload)

    assert len(result.contradicting_evidence) == 1
    assert result.dropped_evidence_count == 0


@pytest.mark.asyncio
async def test_elided_quote_is_kept_when_every_fragment_is_real() -> None:
    service = GeminiService(make_settings())
    payload = make_payload(
        contradicting_evidence=[
            {
                "source_index": 0,
                "quote": "Pakistan defeated India by 180 runs ... It was Pakistan's first Champions Trophy title.",
            }
        ]
    )

    result = await analyze(service, payload)

    assert len(result.contradicting_evidence) == 1


@pytest.mark.asyncio
async def test_elided_quote_is_dropped_when_a_fragment_is_invented() -> None:
    service = GeminiService(make_settings())
    payload = make_payload(
        contradicting_evidence=[
            {
                "source_index": 0,
                "quote": "Pakistan defeated India by 180 runs ... Bangladesh never qualified at all.",
            }
        ]
    )

    result = await analyze(service, payload)

    assert result.contradicting_evidence == []
    assert result.dropped_evidence_count == 1


@pytest.mark.asyncio
async def test_bangla_quote_is_grounded_correctly() -> None:
    service = GeminiService(make_settings())
    bangla = ResearchSource(
        title="ভূমিকম্প",
        url="https://prothomalo.com/x",
        domain="prothomalo.com",
        content="গতকাল ঢাকায় ৫.২ মাত্রার ভূমিকম্প অনুভূত হয়েছে। কোনো হতাহতের খবর পাওয়া যায়নি।",
        source_type=SourceType.NEWS,
        published_date="2026-08-16",
    )
    payload = make_payload(
        verdict="LIKELY_TRUE",
        supporting_evidence=[
            {"source_index": 0, "quote": "ঢাকায় ৫.২ মাত্রার ভূমিকম্প অনুভূত হয়েছে"}
        ],
        contradicting_evidence=[],
    )

    result = await analyze(service, payload, sources=[bangla])

    assert len(result.supporting_evidence) == 1
    assert result.dropped_evidence_count == 0


@pytest.mark.asyncio
async def test_duplicate_quotes_are_collapsed() -> None:
    service = GeminiService(make_settings())
    quote = {"source_index": 0, "quote": "It was Pakistan's first Champions Trophy title."}
    payload = make_payload(contradicting_evidence=[quote, dict(quote)])

    result = await analyze(service, payload)

    assert len(result.contradicting_evidence) == 1


# --- verdict reconciliation -------------------------------------------------


@pytest.mark.asyncio
async def test_likely_true_without_grounded_support_is_downgraded() -> None:
    """A verdict cannot outlive the evidence that justified it."""
    service = GeminiService(make_settings())
    payload = make_payload(
        verdict="LIKELY_TRUE",
        confidence_score=0.95,
        supporting_evidence=[
            {"source_index": 0, "quote": "Bangladesh lifted the trophy in London."}
        ],
        contradicting_evidence=[],
    )

    result = await analyze(service, payload)

    assert result.verdict is Verdict.UNVERIFIED
    assert result.confidence_score <= 0.3
    assert any("unverified rather than true" in note for note in result.important_context)


@pytest.mark.asyncio
async def test_likely_false_without_grounded_contradiction_is_downgraded() -> None:
    service = GeminiService(make_settings())
    payload = make_payload(
        verdict="LIKELY_FALSE",
        confidence_score=0.9,
        contradicting_evidence=[{"source_index": 0, "quote": "Invented contradiction here."}],
    )

    result = await analyze(service, payload)

    assert result.verdict is Verdict.UNVERIFIED
    assert result.confidence_score <= 0.3


@pytest.mark.asyncio
async def test_misleading_verdict_survives_with_grounded_evidence() -> None:
    """MISLEADING is about framing, so it needs evidence but not a contradiction."""
    service = GeminiService(make_settings())
    payload = make_payload(
        verdict="MISLEADING",
        confidence_score=0.7,
        supporting_evidence=[
            {"source_index": 0, "quote": "Bangladesh reached the semi-final stage"}
        ],
        contradicting_evidence=[],
    )

    result = await analyze(service, payload)

    assert result.verdict is Verdict.MISLEADING
    assert result.confidence_score == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_confidence_is_capped_for_a_single_source() -> None:
    service = GeminiService(make_settings())
    payload = make_payload(confidence_score=1.0)

    result = await analyze(service, payload)

    assert result.confidence_score == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_high_confidence_survives_with_several_sources() -> None:
    service = GeminiService(make_settings())
    payload = make_payload(confidence_score=0.9)

    result = await analyze(service, payload, sources=[make_source(0), make_source(1)])

    assert result.confidence_score == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_unverified_with_no_evidence_cannot_be_confident() -> None:
    """Otherwise the UI shows "Unverified" beside "Strong evidence"."""
    service = GeminiService(make_settings())
    payload = make_payload(
        verdict="UNVERIFIED",
        confidence_score=0.95,
        supporting_evidence=[],
        contradicting_evidence=[],
    )

    result = await analyze(service, payload, sources=[make_source(0), make_source(1)])

    assert result.verdict is Verdict.UNVERIFIED
    assert result.confidence_score <= 0.3


@pytest.mark.asyncio
async def test_certainty_is_never_reported() -> None:
    """A few scraped pages cannot put a claim beyond doubt."""
    service = GeminiService(make_settings())
    payload = make_payload(confidence_score=1.0)

    result = await analyze(service, payload, sources=[make_source(0), make_source(1)])

    assert result.confidence_score == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_explanation_instructions_forbid_citing_source_numbers() -> None:
    """The reader never sees source indices, so prose must name publishers."""
    service = GeminiService(make_settings())
    mock = AsyncMock(return_value=stub_response(parsed=make_payload()))

    with patch(TARGET, mock):
        await service.analyze_evidence(make_claim_analysis(), [make_source(0)])

    system = mock.await_args.kwargs["config"].system_instruction
    assert "name publishers, not numbers" in system
    assert 'never "source 4"' in system


@pytest.mark.asyncio
async def test_out_of_range_confidence_is_clamped() -> None:
    """model_copy skips validation, mimicking a model that ignores the stated range."""
    service = GeminiService(make_settings())
    raw = make_payload().model_copy(update={"confidence_score": 4.2})

    result = await analyze(service, raw, sources=[make_source(0), make_source(1)])

    assert result.confidence_score == pytest.approx(0.95)


# --- no evidence ------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_sources_returns_unverified_without_calling_gemini() -> None:
    """Asking the model with no sources invites it to answer from memory."""
    service = GeminiService(make_settings())
    mock = AsyncMock()

    with patch(TARGET, mock):
        result = await service.analyze_evidence(make_claim_analysis(), [])

    mock.assert_not_awaited()
    assert result.verdict is Verdict.UNVERIFIED
    assert result.confidence_score == 0.0
    assert result.supporting_evidence == []
    assert result.important_context


@pytest.mark.asyncio
async def test_all_evidence_dropped_forces_unverified() -> None:
    service = GeminiService(make_settings())
    payload = make_payload(
        verdict="MISLEADING",
        confidence_score=0.8,
        supporting_evidence=[{"source_index": 0, "quote": "Invented supporting line."}],
        contradicting_evidence=[{"source_index": 0, "quote": "Invented contradicting line."}],
    )

    result = await analyze(service, payload)

    assert result.verdict is Verdict.UNVERIFIED
    assert result.dropped_evidence_count == 2
    assert result.confidence_score <= 0.3


# --- failure modes ----------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_api_key_raises_service_unavailable() -> None:
    from app.utils.errors import ServiceUnavailableError

    service = GeminiService(make_settings(gemini_api_key=None))

    with pytest.raises(ServiceUnavailableError):
        await service.analyze_evidence(make_claim_analysis(), [make_source(0)])


@pytest.mark.asyncio
async def test_malformed_payload_raises_service_error() -> None:
    from app.utils.errors import ServiceError

    service = GeminiService(make_settings())

    with patch(TARGET, AsyncMock(return_value=stub_response(parsed={"verdict": "MAYBE"}))):
        with pytest.raises(ServiceError):
            await service.analyze_evidence(make_claim_analysis(), [make_source(0)])


@pytest.mark.asyncio
async def test_invalid_verdict_value_is_rejected() -> None:
    """An unknown verdict string must fail loudly, not pass through to the frontend."""
    from app.utils.errors import ServiceError

    service = GeminiService(make_settings())
    bad = {**make_payload().model_dump(mode="json"), "verdict": "PROBABLY_TRUE"}

    with patch(TARGET, AsyncMock(return_value=stub_response(parsed=bad))):
        with pytest.raises(ServiceError):
            await service.analyze_evidence(make_claim_analysis(), [make_source(0)])


@pytest.mark.asyncio
async def test_empty_explanation_is_rejected() -> None:
    from app.utils.errors import ServiceError

    service = GeminiService(make_settings())
    payload = make_payload().model_copy(update={"short_explanation": "   "})

    with patch(TARGET, AsyncMock(return_value=stub_response(parsed=payload))):
        with pytest.raises(ServiceError):
            await service.analyze_evidence(make_claim_analysis(), [make_source(0)])


@pytest.mark.asyncio
async def test_no_urls_are_ever_taken_from_the_model() -> None:
    """The model cannot emit a URL, so a fabricated link is unrepresentable."""
    service = GeminiService(make_settings())
    real_url = "https://en.wikipedia.org/wiki/2017_Champions_Trophy"
    payload = make_payload(
        source_assessments=[
            {
                "source_index": 0,
                "stance": "contradicts",
                "reliability": "medium",
                "is_outdated": False,
                # Even if the model smuggles a URL into free text, it is truncated
                # into the note and never used as the source's identity.
                "note": "See https://evil.example.com/fabricated for details.",
            }
        ]
    )

    result = await analyze(service, payload, sources=[make_source(0)])

    assert result.source_assessments[0].url == real_url
    # The only URL identifying a source is the one Firecrawl actually retrieved.
    urls = {assessment.url for assessment in result.source_assessments}
    assert urls == {real_url}
