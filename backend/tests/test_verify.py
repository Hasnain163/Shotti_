"""End-to-end tests for POST /api/verify with both external services mocked.

Gemini and Firecrawl are replaced through FastAPI's dependency overrides, so the
real pipeline, response projection, and error handling all run — only the network
calls are stubbed. No API keys, no network, no credits.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_firecrawl_service, get_gemini_service
from app.main import app
from app.models.analysis import EvidenceAnalysis
from app.models.claim import ClaimAnalysis, ClaimTopic, DetectedLanguage
from app.models.evidence import EvidenceItem, Reliability, SourceAssessment, Stance
from app.models.source import FailedSource, ResearchBundle, ResearchSource, SourceType
from app.models.verify import Verdict
from app.utils.errors import (
    RateLimitError,
    ServiceError,
    ServiceUnavailableError,
)

SOURCE_TEXT = (
    "Pakistan defeated India by 180 runs in the final of the 2017 ICC Champions "
    "Trophy at The Oval. Bangladesh reached the semi-final and were eliminated."
)


def make_claim_analysis(**overrides) -> ClaimAnalysis:
    defaults = {
        "original_claim": "Bangladesh won the ICC Champions Trophy in 2017.",
        "normalized_claim": "Bangladesh won the 2017 ICC Champions Trophy.",
        "language": DetectedLanguage.ENGLISH,
        "topic": ClaimTopic.SPORTS,
        "entities": ["Bangladesh"],
        "temporal_references": ["2017"],
        "resolved_timeframe": "2017",
        "factual_proposition": "Bangladesh won the 2017 ICC Champions Trophy.",
        "verification_questions": ["Who won the 2017 ICC Champions Trophy?"],
        "search_queries": ["2017 Champions Trophy winner", "চ্যাম্পিয়ন্স ট্রফি ২০১৭"],
        "is_checkable": True,
    }
    return ClaimAnalysis(**{**defaults, **overrides})


def make_source(**overrides) -> ResearchSource:
    defaults = {
        "title": "2017 Champions Trophy",
        "url": "https://en.wikipedia.org/wiki/2017_Champions_Trophy",
        "domain": "en.wikipedia.org",
        "content": SOURCE_TEXT,
        "source_type": SourceType.ENCYCLOPEDIA,
        "published_date": "2017-06-19",
        "snippet": "Pakistan won the 2017 final.",
        "credibility": 80,
        "found_by_query": "2017 Champions Trophy winner",
    }
    return ResearchSource(**{**defaults, **overrides})


def make_bundle(sources=None, **overrides) -> ResearchBundle:
    defaults = {
        "sources": sources if sources is not None else [make_source()],
        "failures": [],
        "queries_used": ["2017 Champions Trophy winner"],
        "queries_failed": [],
        "candidates_found": 8,
        "total_content_chars": len(SOURCE_TEXT),
        "degraded": False,
    }
    return ResearchBundle(**{**defaults, **overrides})


def make_evidence_analysis(**overrides) -> EvidenceAnalysis:
    defaults = {
        "verdict": Verdict.LIKELY_FALSE,
        "confidence_score": 0.88,
        "short_explanation": "Pakistan won the 2017 Champions Trophy, not Bangladesh.",
        "supporting_evidence": [],
        "contradicting_evidence": [
            EvidenceItem(quote="Pakistan defeated India by 180 runs", source_index=0)
        ],
        "important_context": ["Bangladesh reached the semi-final."],
        "source_assessments": [
            SourceAssessment(
                source_index=0,
                url="https://en.wikipedia.org/wiki/2017_Champions_Trophy",
                domain="en.wikipedia.org",
                stance=Stance.CONTRADICTS,
                reliability=Reliability.MEDIUM,
                is_outdated=False,
                published_date="2017-06-19",
                note="States the tournament winner.",
            )
        ],
        "has_conflicting_evidence": False,
        "relies_on_speculation": False,
        "dropped_evidence_count": 0,
    }
    return EvidenceAnalysis(**{**defaults, **overrides})


def install(
    claim_result=None,
    research_result=None,
    evidence_result=None,
) -> tuple[SimpleNamespace, SimpleNamespace]:
    """Override both services with mocks. Values may be results or exceptions."""

    def as_mock(value, default):
        target = default if value is None else value
        if isinstance(target, BaseException):
            return AsyncMock(side_effect=target)
        return AsyncMock(return_value=target)

    gemini = SimpleNamespace(
        analyze_claim=as_mock(claim_result, make_claim_analysis()),
        analyze_evidence=as_mock(evidence_result, make_evidence_analysis()),
    )
    firecrawl = SimpleNamespace(research=as_mock(research_result, make_bundle()))

    app.dependency_overrides[get_gemini_service] = lambda: gemini
    app.dependency_overrides[get_firecrawl_service] = lambda: firecrawl
    return gemini, firecrawl


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# --- the full contract ------------------------------------------------------


def test_returns_the_full_documented_contract(client: TestClient) -> None:
    install()
    response = client.post("/api/verify", json={"claim": "Bangladesh won the ICC Champions Trophy in 2017."})

    assert response.status_code == 200
    body = response.json()

    for field in (
        "claim",
        "normalized_claim",
        "verdict",
        "confidence_score",
        "explanation",
        "supporting_evidence",
        "contradicting_evidence",
        "important_context",
        "sources",
    ):
        assert field in body, f"missing contract field: {field}"

    assert body["claim"] == "Bangladesh won the ICC Champions Trophy in 2017."
    assert body["normalized_claim"] == "Bangladesh won the 2017 ICC Champions Trophy."
    assert body["verdict"] == "LIKELY_FALSE"
    assert body["confidence_score"] == pytest.approx(0.88)
    assert body["explanation"]
    assert body["important_context"] == ["Bangladesh reached the semi-final."]


def test_verdict_is_always_one_of_the_four(client: TestClient) -> None:
    for verdict in Verdict:
        install(evidence_result=make_evidence_analysis(verdict=verdict))
        body = client.post("/api/verify", json={"claim": "A checkable claim here."}).json()
        assert body["verdict"] in {
            "LIKELY_TRUE",
            "LIKELY_FALSE",
            "UNVERIFIED",
            "MISLEADING",
        }


def test_stages_run_in_order_with_the_right_inputs(client: TestClient) -> None:
    gemini, firecrawl = install()
    client.post("/api/verify", json={"claim": "Bangladesh won the ICC Champions Trophy in 2017."})

    # Claim analysis receives the raw claim.
    assert gemini.analyze_claim.await_args.kwargs["claim"].startswith("Bangladesh won")

    # Research receives the queries that claim analysis generated.
    assert firecrawl.research.await_args.args[0] == [
        "2017 Champions Trophy winner",
        "চ্যাম্পিয়ন্স ট্রফি ২০১৭",
    ]

    # Evidence analysis receives the scraped sources.
    evidence_kwargs = gemini.analyze_evidence.await_args.kwargs
    assert [source.url for source in evidence_kwargs["sources"]] == [
        "https://en.wikipedia.org/wiki/2017_Champions_Trophy"
    ]


def test_sources_are_projected_without_internal_fields(client: TestClient) -> None:
    """Scraped page content and ranking scores must stay server-side."""
    install()
    body = client.post("/api/verify", json={"claim": "A checkable claim here."}).json()

    assert len(body["sources"]) == 1
    source = body["sources"][0]
    assert source["url"] == "https://en.wikipedia.org/wiki/2017_Champions_Trophy"
    assert source["domain"] == "en.wikipedia.org"
    assert source["published_date"] == "2017-06-19"
    assert source["source_type"] == "encyclopedia"
    for internal in ("content", "credibility", "found_by_query"):
        assert internal not in source
    assert SOURCE_TEXT not in response_text(body)


def test_evidence_references_a_retrieved_source(client: TestClient) -> None:
    install()
    body = client.post("/api/verify", json={"claim": "A checkable claim here."}).json()

    for item in body["supporting_evidence"] + body["contradicting_evidence"]:
        assert 0 <= item["source_index"] < len(body["sources"])


def test_no_urls_beyond_the_retrieved_sources(client: TestClient) -> None:
    """A URL in the response can only be one Firecrawl actually returned."""
    install()
    body = client.post("/api/verify", json={"claim": "A checkable claim here."}).json()

    allowed = {source["url"] for source in body["sources"]}
    text = response_text(body)
    for url in allowed:
        text = text.replace(url, "")
    assert "http://" not in text and "https://" not in text


def test_response_never_contains_api_keys(client: TestClient) -> None:
    install()
    raw = client.post("/api/verify", json={"claim": "A checkable claim here."}).text.lower()

    for forbidden in ("api_key", "gemini_api", "firecrawl_api", "sk_", "fc-", "aiza"):
        assert forbidden not in raw


def test_meta_reports_how_the_run_went(client: TestClient) -> None:
    install()
    body = client.post("/api/verify", json={"claim": "A checkable claim here."}).json()

    meta = body["meta"]
    assert meta["sources_used"] == 1
    assert meta["sources_found"] == 8
    assert meta["queries_used"] == 1
    assert meta["duration_ms"] >= 0
    assert meta["degraded"] is False


# --- honest handling of insufficient evidence --------------------------------


def test_no_sources_yields_unverified_not_a_guess(client: TestClient) -> None:
    install(
        research_result=make_bundle(sources=[], candidates_found=0, degraded=True),
        evidence_result=EvidenceAnalysis.unverified(
            explanation="No usable sources could be retrieved for this claim.",
            context=["No web sources were available to check this claim against."],
        ),
    )

    body = client.post("/api/verify", json={"claim": "An obscure unverifiable claim."}).json()

    assert body["verdict"] == "UNVERIFIED"
    assert body["confidence_score"] == 0.0
    assert body["sources"] == []
    assert body["supporting_evidence"] == []
    assert body["contradicting_evidence"] == []
    assert body["important_context"]
    assert body["meta"]["degraded"] is True


def test_uncheckable_claim_skips_research_entirely(client: TestClient) -> None:
    """An opinion cannot be researched, so no credits are spent on it."""
    gemini, firecrawl = install(
        claim_result=make_claim_analysis(
            is_checkable=False,
            uncheckable_reason="This is a personal opinion, so no evidence could settle it.",
            search_queries=[],
        )
    )

    body = client.post("/api/verify", json={"claim": "Biryani is the best food ever."}).json()

    firecrawl.research.assert_not_awaited()
    gemini.analyze_evidence.assert_not_awaited()
    assert body["verdict"] == "UNVERIFIED"
    assert body["confidence_score"] == 0.0
    assert "opinion" in body["explanation"].lower()


def test_no_search_queries_returns_unverified(client: TestClient) -> None:
    gemini, firecrawl = install(claim_result=make_claim_analysis(search_queries=[]))

    body = client.post("/api/verify", json={"claim": "A claim with no queries."}).json()

    firecrawl.research.assert_not_awaited()
    assert body["verdict"] == "UNVERIFIED"
    assert body["meta"]["degraded"] is True


def test_partial_research_is_marked_degraded(client: TestClient) -> None:
    install(
        research_result=make_bundle(
            failures=[FailedSource(url="https://ft.com/a", domain="ft.com", reason="paywall")],
            queries_failed=["failed query"],
            degraded=True,
        )
    )

    body = client.post("/api/verify", json={"claim": "A checkable claim here."}).json()

    assert body["meta"]["degraded"] is True
    # Failures are diagnostics; they must not appear as evidence.
    assert "paywall" not in response_text(body)


def test_dropped_evidence_is_reported_in_meta(client: TestClient) -> None:
    install(evidence_result=make_evidence_analysis(dropped_evidence_count=2))

    body = client.post("/api/verify", json={"claim": "A checkable claim here."}).json()

    assert body["meta"]["dropped_evidence_count"] == 2
    assert body["meta"]["degraded"] is True


def test_conflict_and_speculation_flags_surface(client: TestClient) -> None:
    install(
        evidence_result=make_evidence_analysis(
            verdict=Verdict.UNVERIFIED,
            has_conflicting_evidence=True,
            relies_on_speculation=True,
        )
    )

    body = client.post("/api/verify", json={"claim": "A contested claim here."}).json()

    assert body["meta"]["has_conflicting_evidence"] is True
    assert body["meta"]["relies_on_speculation"] is True


# --- request validation -----------------------------------------------------


def test_bangla_claim_round_trips(client: TestClient) -> None:
    claim = "বাংলাদেশের রাজধানী ঢাকা।"
    install(claim_result=make_claim_analysis(original_claim=claim, language=DetectedLanguage.BANGLA))

    body = client.post("/api/verify", json={"claim": claim, "language": "bn"}).json()

    assert body["claim"] == claim
    assert body["language"] == "bn"


def test_claim_id_is_stable_across_requests(client: TestClient) -> None:
    install()
    first = client.post("/api/verify", json={"claim": "Water boils at 100C."}).json()
    install()
    second = client.post("/api/verify", json={"claim": "  water boils at 100C.  "}).json()

    assert first["claim_id"] == second["claim_id"]


@pytest.mark.parametrize(
    "payload",
    [
        {"claim": "  "},
        {},
        {"claim": "x" * 1001},
        {"claim": "A real claim.", "language": "fr"},
    ],
)
def test_invalid_requests_are_rejected(client: TestClient, payload: dict) -> None:
    install()
    response = client.post("/api/verify", json=payload)

    assert response.status_code == 422
    assert response.json()["error"] in {"validation_error", "invalid_claim"}


# --- upstream failures ------------------------------------------------------


def test_missing_api_key_returns_503(client: TestClient) -> None:
    install(claim_result=ServiceUnavailableError("GEMINI_API_KEY is not configured."))
    response = client.post("/api/verify", json={"claim": "A checkable claim here."})

    assert response.status_code == 503
    assert response.json()["error"] == "service_unavailable"


def test_rate_limit_returns_429_with_retry_advice(client: TestClient) -> None:
    install(research_result=RateLimitError("Rate limit reached. Please wait a moment."))
    response = client.post("/api/verify", json={"claim": "A checkable claim here."})

    assert response.status_code == 429
    body = response.json()
    assert body["error"] == "rate_limited"
    assert "wait" in body["message"].lower()


def test_upstream_failure_returns_502(client: TestClient) -> None:
    install(evidence_result=ServiceError("The AI service could not analyse this claim."))
    response = client.post("/api/verify", json={"claim": "A checkable claim here."})

    assert response.status_code == 502
    assert response.json()["error"] == "service_error"


def test_unexpected_error_does_not_leak_internals(client: TestClient) -> None:
    install(claim_result=RuntimeError("boom: internal detail at /secret/path"))

    with pytest.raises(RuntimeError):
        # TestClient re-raises by default; the handler still shapes the response
        # for real clients, which test_health covers via the 404 envelope.
        client.post("/api/verify", json={"claim": "A checkable claim here."})


def test_unexpected_error_is_shaped_for_real_clients(client: TestClient) -> None:
    install(claim_result=RuntimeError("boom: internal detail at /secret/path"))
    quiet = TestClient(app, raise_server_exceptions=False)

    response = quiet.post("/api/verify", json={"claim": "A checkable claim here."})

    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "internal_error"
    assert "secret" not in response.text
    assert "boom" not in response.text


def response_text(body: dict) -> str:
    import json

    return json.dumps(body, ensure_ascii=False)
