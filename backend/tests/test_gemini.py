"""Tests for the Gemini claim analysis agent.

Every test here is mocked — the suite must pass with no GEMINI_API_KEY set and
must never make a network call. The single live test lives in test_gemini_live.py
and is opt-in.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from google.genai import errors as genai_errors

from app.config import Settings
from app.models.claim import ClaimAnalysis, ClaimTopic, DetectedLanguage, GeminiClaimPayload
from app.services.gemini import GeminiService
from app.utils.errors import RateLimitError, ServiceError, ServiceUnavailableError


@pytest_asyncio.fixture(autouse=True)
async def close_gemini_clients():
    """Close any SDK client a test created.

    Tracking instances via __init__ keeps this out of every test signature. Without
    it the SDK leaves an unawaited aclose() coroutine behind at garbage collection,
    which surfaces as a RuntimeWarning storm that hides real warnings.
    """
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
    """Settings that ignore the developer's real .env, so tests are deterministic."""
    defaults = {
        "gemini_api_key": "test-key-not-real",
        "gemini_model": "gemini-3.7-flash",
        "gemini_timeout_ms": 1000,
        "gemini_max_retries": 2,
        # No real waiting in tests.
        "gemini_retry_backoff_seconds": 0.0,
        "firecrawl_api_key": None,
        "elevenlabs_api_key": None,
        "cors_origins": ["http://localhost:5173"],
    }
    return Settings(**{**defaults, **overrides})


def make_payload(**overrides) -> GeminiClaimPayload:
    defaults = {
        "normalized_claim": "Dhaka is the capital of Bangladesh.",
        "language": "bn",
        "topic": "politics",
        "entities": ["Dhaka", "Bangladesh"],
        "temporal_references": [],
        "resolved_timeframe": None,
        "factual_proposition": "The capital city of Bangladesh is Dhaka.",
        "verification_questions": ["Which city is designated the capital of Bangladesh?"],
        "search_queries": ["capital of Bangladesh", "বাংলাদেশের রাজধানী"],
        "is_checkable": True,
        "uncheckable_reason": None,
    }
    return GeminiClaimPayload(**{**defaults, **overrides})


def stub_response(parsed=None, text: str | None = None) -> SimpleNamespace:
    """Mimic the shape of an SDK GenerateContentResponse."""
    return SimpleNamespace(parsed=parsed, text=text)


def patched_call(response) -> AsyncMock:
    """Patch the async SDK entrypoint, returning the mock for assertions."""
    mock = AsyncMock(return_value=response)
    return patch("google.genai.models.AsyncModels.generate_content", mock)


# --- happy path -------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_claim_returns_investigation_plan() -> None:
    service = GeminiService(make_settings())
    claim = "বাংলাদেশের রাজধানী ঢাকা।"

    with patched_call(stub_response(parsed=make_payload())):
        result = await service.analyze_claim(claim)

    assert isinstance(result, ClaimAnalysis)
    assert result.original_claim == claim
    assert result.normalized_claim == "Dhaka is the capital of Bangladesh."
    assert result.language is DetectedLanguage.BANGLA
    assert result.topic is ClaimTopic.POLITICS
    assert result.entities == ["Dhaka", "Bangladesh"]
    assert result.factual_proposition
    assert result.verification_questions
    assert result.search_queries
    assert result.is_checkable is True


@pytest.mark.asyncio
async def test_analysis_carries_no_verdict() -> None:
    """This stage must not leak a truth judgement into the contract."""
    service = GeminiService(make_settings())

    with patched_call(stub_response(parsed=make_payload())):
        result = await service.analyze_claim("Some claim about something.")

    for forbidden in ("verdict", "confidence", "is_true", "supporting_evidence"):
        assert forbidden not in result.model_dump()


@pytest.mark.asyncio
async def test_prompt_includes_claim_and_injected_date() -> None:
    service = GeminiService(make_settings())
    mock = AsyncMock(return_value=stub_response(parsed=make_payload()))

    with patch("google.genai.models.AsyncModels.generate_content", mock):
        await service.analyze_claim("Rice prices doubled.", today=date(2026, 8, 17))

    kwargs = mock.await_args.kwargs
    assert "Rice prices doubled." in kwargs["contents"]
    assert "2026-08-17" in kwargs["contents"]
    assert kwargs["model"] == "gemini-3.7-flash"
    # Structured output and deterministic decoding are both load-bearing.
    assert kwargs["config"].response_schema is GeminiClaimPayload
    assert kwargs["config"].temperature == 0.0
    assert "MUST NOT decide whether the claim is true" in kwargs["config"].system_instruction


@pytest.mark.asyncio
async def test_requested_language_is_passed_but_not_trusted() -> None:
    service = GeminiService(make_settings())
    mock = AsyncMock(return_value=stub_response(parsed=make_payload()))

    with patch("google.genai.models.AsyncModels.generate_content", mock):
        await service.analyze_claim("A claim.", requested_language="bn")

    contents = mock.await_args.kwargs["contents"]
    assert "bn" in contents
    assert "Verify this yourself" in contents


@pytest.mark.asyncio
async def test_uncheckable_claim_is_reported_not_judged() -> None:
    service = GeminiService(make_settings())
    payload = make_payload(
        is_checkable=False,
        uncheckable_reason="This is a personal opinion, so no evidence could settle it.",
    )

    with patched_call(stub_response(parsed=payload)):
        result = await service.analyze_claim("Biryani is the best food.")

    assert result.is_checkable is False
    assert result.uncheckable_reason


# --- normalisation of model output ------------------------------------------


@pytest.mark.asyncio
async def test_lists_are_deduped_stripped_and_capped() -> None:
    service = GeminiService(make_settings())
    payload = make_payload(
        entities=["  Dhaka  ", "dhaka", "DHAKA", "", "Bangladesh"],
        search_queries=[f"query {i}" for i in range(20)],
    )

    with patched_call(stub_response(parsed=payload)):
        result = await service.analyze_claim("A claim.")

    assert result.entities == ["Dhaka", "Bangladesh"]
    assert len(result.search_queries) == 5


@pytest.mark.asyncio
async def test_blank_optional_strings_become_none() -> None:
    service = GeminiService(make_settings())
    payload = make_payload(resolved_timeframe="   ", uncheckable_reason="")

    with patched_call(stub_response(parsed=payload)):
        result = await service.analyze_claim("A claim.")

    assert result.resolved_timeframe is None
    assert result.uncheckable_reason is None


@pytest.mark.asyncio
async def test_dict_parsed_payload_is_accepted() -> None:
    """Some SDK paths hand back a plain dict rather than the model instance."""
    service = GeminiService(make_settings())

    with patched_call(stub_response(parsed=make_payload().model_dump())):
        result = await service.analyze_claim("A claim.")

    assert result.normalized_claim == "Dhaka is the capital of Bangladesh."


@pytest.mark.asyncio
async def test_falls_back_to_raw_text_when_parsed_is_none() -> None:
    service = GeminiService(make_settings())
    raw = make_payload().model_dump_json()

    with patched_call(stub_response(parsed=None, text=raw)):
        result = await service.analyze_claim("A claim.")

    assert result.normalized_claim == "Dhaka is the capital of Bangladesh."


# --- failure modes ----------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_api_key_raises_service_unavailable() -> None:
    service = GeminiService(make_settings(gemini_api_key=None))

    with pytest.raises(ServiceUnavailableError) as exc:
        await service.analyze_claim("A claim.")

    assert "GEMINI_API_KEY" in exc.value.message


@pytest.mark.asyncio
async def test_missing_api_key_makes_no_network_call() -> None:
    service = GeminiService(make_settings(gemini_api_key=None))
    mock = AsyncMock()

    with patch("google.genai.models.AsyncModels.generate_content", mock):
        with pytest.raises(ServiceUnavailableError):
            await service.analyze_claim("A claim.")

    mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_response_raises_service_error() -> None:
    service = GeminiService(make_settings())

    with patched_call(stub_response(parsed=None, text="")):
        with pytest.raises(ServiceError):
            await service.analyze_claim("A claim.")


@pytest.mark.asyncio
async def test_prose_response_raises_service_error() -> None:
    service = GeminiService(make_settings())

    with patched_call(stub_response(parsed=None, text="Sure! Here is the analysis:")):
        with pytest.raises(ServiceError):
            await service.analyze_claim("A claim.")


@pytest.mark.asyncio
async def test_schema_violation_raises_service_error() -> None:
    """A payload missing a required field must fail loudly, not silently pass through."""
    service = GeminiService(make_settings())
    incomplete = {"normalized_claim": "x", "language": "en"}

    with patched_call(stub_response(parsed=incomplete)):
        with pytest.raises(ServiceError):
            await service.analyze_claim("A claim.")


@pytest.mark.asyncio
async def test_client_error_is_wrapped_with_actionable_message() -> None:
    service = GeminiService(make_settings())
    error = genai_errors.ClientError(400, {"error": {"message": "API key not valid"}})

    with patch("google.genai.models.AsyncModels.generate_content", AsyncMock(side_effect=error)):
        with pytest.raises(ServiceError) as exc:
            await service.analyze_claim("A claim.")

    assert "Gemini API key" in exc.value.message


@pytest.mark.asyncio
async def test_transient_server_error_is_retried_then_succeeds() -> None:
    """A 503 'high demand' is the common live failure; it must not surface to the user."""
    service = GeminiService(make_settings())
    error = genai_errors.ServerError(503, {"error": {"message": "high demand"}})
    mock = AsyncMock(side_effect=[error, stub_response(parsed=make_payload())])

    with patch("google.genai.models.AsyncModels.generate_content", mock):
        result = await service.analyze_claim("A claim.")

    assert result.normalized_claim == "Dhaka is the capital of Bangladesh."
    assert mock.await_count == 2


@pytest.mark.asyncio
async def test_persistent_server_error_gives_up_after_configured_attempts() -> None:
    service = GeminiService(make_settings(gemini_max_retries=2))
    error = genai_errors.ServerError(503, {"error": {"message": "high demand"}})
    mock = AsyncMock(side_effect=error)

    with patch("google.genai.models.AsyncModels.generate_content", mock):
        with pytest.raises(ServiceError) as exc:
            await service.analyze_claim("A claim.")

    assert mock.await_count == 3  # 1 initial + 2 retries
    assert "try again" in exc.value.message.lower()


@pytest.mark.asyncio
async def test_client_error_is_never_retried() -> None:
    """Retrying a bad key or exhausted quota just delays the real message."""
    service = GeminiService(make_settings())
    error = genai_errors.ClientError(400, {"error": {"message": "API key not valid"}})
    mock = AsyncMock(side_effect=error)

    with patch("google.genai.models.AsyncModels.generate_content", mock):
        with pytest.raises(ServiceError):
            await service.analyze_claim("A claim.")

    assert mock.await_count == 1


@pytest.mark.asyncio
async def test_rate_limit_is_its_own_error_not_a_config_problem() -> None:
    """Free-tier Gemini 429s constantly; the message must say 'wait', not 'check your key'."""
    service = GeminiService(make_settings())
    error = genai_errors.ClientError(429, {"error": {"message": "RESOURCE_EXHAUSTED"}})
    mock = AsyncMock(side_effect=error)

    with patch("google.genai.models.AsyncModels.generate_content", mock):
        with pytest.raises(RateLimitError) as exc:
            await service.analyze_claim("A claim.")

    assert exc.value.status_code == 429
    assert exc.value.error_code == "rate_limited"
    assert "wait" in exc.value.message.lower()
    assert "api key" not in exc.value.message.lower()
    assert mock.await_count == 1  # the wait is too long to retry inline


@pytest.mark.asyncio
async def test_retries_can_be_disabled() -> None:
    service = GeminiService(make_settings(gemini_max_retries=0))
    error = genai_errors.ServerError(503, {"error": {"message": "high demand"}})
    mock = AsyncMock(side_effect=error)

    with patch("google.genai.models.AsyncModels.generate_content", mock):
        with pytest.raises(ServiceError):
            await service.analyze_claim("A claim.")

    assert mock.await_count == 1


@pytest.mark.asyncio
async def test_network_failure_is_wrapped_not_leaked() -> None:
    """Raw exceptions must never escape as 500s with internal detail."""
    service = GeminiService(make_settings())

    with patch(
        "google.genai.models.AsyncModels.generate_content",
        AsyncMock(side_effect=TimeoutError("connection timed out")),
    ):
        with pytest.raises(ServiceError) as exc:
            await service.analyze_claim("A claim.")

    assert "connection timed out" not in exc.value.message
