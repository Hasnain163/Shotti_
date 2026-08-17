"""Tests for the screenshot verification workflow.

Fully mocked. Real image bytes are used for the validation layer (so magic-byte
sniffing is genuinely exercised), while Gemini and Firecrawl are replaced through
dependency overrides.
"""

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_firecrawl_service, get_gemini_service
from app.main import app
from app.models.claim import DetectedLanguage
from app.models.screenshot import (
    GeminiScreenshotPayload,
    ScreenshotExtraction,
    ScreenshotKind,
)
from app.utils.errors import RateLimitError, ServiceError, ServiceUnavailableError
from app.utils.images import (
    MIN_IMAGE_BYTES,
    sniff_image_mime,
    validate_image,
)
from tests.test_verify import (
    install,
    make_bundle,
    make_claim_analysis,
    make_evidence_analysis,
)

# --- real image bytes -------------------------------------------------------
# Minimal but structurally valid headers, padded past MIN_IMAGE_BYTES so the size
# floor does not reject them.

PAD = b"\x00" * MIN_IMAGE_BYTES
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + PAD
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00\x10JFIF\x00" + PAD
WEBP_BYTES = b"RIFF" + b"\x24\x00\x00\x00" + b"WEBPVP8 " + PAD
GIF_BYTES = b"GIF89a" + b"\x01\x00\x01\x00" + PAD
PDF_BYTES = b"%PDF-1.7\n%\xc7\xec\x8f\xa2" + PAD
TEXT_BYTES = b"this is not an image at all, just plain text" + PAD


def make_extraction(**overrides) -> ScreenshotExtraction:
    defaults = {
        "extracted_text": (
            "ব্রেকিং: গতকাল ঢাকায় ৭ মাত্রার ভূমিকম্প হয়েছে। প্রথম আলো · ৩ ঘণ্টা আগে"
        ),
        "primary_claim": "গতকাল ঢাকায় ৭ মাত্রার ভূমিকম্প হয়েছে।",
        "language": DetectedLanguage.BANGLA,
        "kind": ScreenshotKind.SOCIAL_POST,
        "visible_date": "৩ ঘণ্টা আগে",
        "visible_source": "প্রথম আলো",
        "has_factual_claim": True,
        "notes": None,
    }
    return ScreenshotExtraction(**{**defaults, **overrides})


def install_screenshot(extract_result=None, **kwargs):
    """Extend the text-pipeline mocks with an image-reading mock."""
    gemini, firecrawl = install(**kwargs)
    target = make_extraction() if extract_result is None else extract_result
    gemini.extract_claim_from_image = (
        AsyncMock(side_effect=target)
        if isinstance(target, BaseException)
        else AsyncMock(return_value=target)
    )
    app.dependency_overrides[get_gemini_service] = lambda: gemini
    app.dependency_overrides[get_firecrawl_service] = lambda: firecrawl
    return gemini, firecrawl


def upload(data: bytes, filename: str = "shot.png", content_type: str = "image/png"):
    return {"image": (filename, io.BytesIO(data), content_type)}


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# --- validation layer -------------------------------------------------------


class TestImageValidation:
    def test_sniffs_every_supported_format(self) -> None:
        assert sniff_image_mime(PNG_BYTES) == "image/png"
        assert sniff_image_mime(JPEG_BYTES) == "image/jpeg"
        assert sniff_image_mime(WEBP_BYTES) == "image/webp"
        assert sniff_image_mime(GIF_BYTES) == "image/gif"

    def test_rejects_non_images(self) -> None:
        assert sniff_image_mime(PDF_BYTES) is None
        assert sniff_image_mime(TEXT_BYTES) is None
        assert sniff_image_mime(b"") is None

    def test_true_type_wins_over_a_wrong_declared_type(self) -> None:
        """Android share sheets mislabel files, so the bytes decide."""
        assert validate_image(JPEG_BYTES, "image/png", 5_000_000) == "image/jpeg"

    def test_pdf_renamed_as_png_is_rejected(self) -> None:
        from app.utils.errors import UnsupportedMediaTypeError

        with pytest.raises(UnsupportedMediaTypeError):
            validate_image(PDF_BYTES, "image/png", 5_000_000)

    def test_oversize_is_rejected(self) -> None:
        from app.utils.errors import PayloadTooLargeError

        with pytest.raises(PayloadTooLargeError) as exc:
            validate_image(PNG_BYTES + b"\x00" * 5_000_000, "image/png", 1_000)

        assert exc.value.status_code == 413

    def test_empty_and_truncated_uploads_are_rejected(self) -> None:
        from app.utils.errors import UnsupportedMediaTypeError

        for data in (b"", b"\x89PNG"):
            with pytest.raises(UnsupportedMediaTypeError):
                validate_image(data, "image/png", 5_000_000)


# --- extraction endpoint ----------------------------------------------------


def test_extract_returns_the_claim_and_visible_metadata(client: TestClient) -> None:
    install_screenshot()
    response = client.post("/api/screenshot/extract", files=upload(PNG_BYTES))

    assert response.status_code == 200
    body = response.json()
    extraction = body["extraction"]

    assert extraction["primary_claim"] == "গতকাল ঢাকায় ৭ মাত্রার ভূমিকম্প হয়েছে।"
    assert extraction["extracted_text"]
    assert extraction["visible_date"] == "৩ ঘণ্টা আগে"
    assert extraction["visible_source"] == "প্রথম আলো"
    assert extraction["language"] == "bn"
    assert extraction["kind"] == "social_post"
    assert body["suggested_claim"] == extraction["primary_claim"]


def test_extract_performs_no_research_and_returns_no_verdict(client: TestClient) -> None:
    _, firecrawl = install_screenshot()
    body = client.post("/api/screenshot/extract", files=upload(PNG_BYTES)).json()

    firecrawl.research.assert_not_awaited()
    assert "verdict" not in body


def test_extract_receives_the_sniffed_mime_type(client: TestClient) -> None:
    gemini, _ = install_screenshot()
    # Declared png, actually jpeg.
    client.post("/api/screenshot/extract", files=upload(JPEG_BYTES, "shot.png", "image/png"))

    kwargs = gemini.extract_claim_from_image.await_args.kwargs
    assert kwargs["mime_type"] == "image/jpeg"
    assert kwargs["image_bytes"] == JPEG_BYTES


@pytest.mark.parametrize(
    ("data", "content_type"),
    [
        (PNG_BYTES, "image/png"),
        (JPEG_BYTES, "image/jpeg"),
        (WEBP_BYTES, "image/webp"),
        (GIF_BYTES, "image/gif"),
    ],
)
def test_every_supported_format_is_accepted(client: TestClient, data, content_type) -> None:
    install_screenshot()
    response = client.post(
        "/api/screenshot/extract", files=upload(data, "shot", content_type)
    )
    assert response.status_code == 200


# --- full workflow ----------------------------------------------------------


def test_full_workflow_produces_a_verdict_and_shows_what_was_read(
    client: TestClient,
) -> None:
    install_screenshot()
    response = client.post("/api/verify/screenshot", files=upload(PNG_BYTES))

    assert response.status_code == 200
    body = response.json()

    # The same verdict contract as a typed claim.
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

    assert body["verdict"] in {"LIKELY_TRUE", "LIKELY_FALSE", "UNVERIFIED", "MISLEADING"}
    # Plus what was read from the image, so the user can see it.
    assert body["extraction"]["primary_claim"] == body["claim"]
    assert body["extraction"]["visible_date"] == "৩ ঘণ্টা আগে"


def test_workflow_reuses_the_existing_pipeline_stages(client: TestClient) -> None:
    """The image adds one stage on the front; nothing after it is duplicated."""
    gemini, firecrawl = install_screenshot()
    client.post("/api/verify/screenshot", files=upload(PNG_BYTES))

    gemini.extract_claim_from_image.assert_awaited_once()
    # The extracted claim, not the raw image, drives claim analysis.
    assert (
        gemini.analyze_claim.await_args.kwargs["claim"]
        == "গতকাল ঢাকায় ৭ মাত্রার ভূমিকম্প হয়েছে।"
    )
    firecrawl.research.assert_awaited_once()
    gemini.analyze_evidence.assert_awaited_once()


def test_extracted_claim_language_is_detected_not_forced(client: TestClient) -> None:
    """Claim analysis re-detects language from the text, so stages cannot disagree."""
    gemini, _ = install_screenshot()
    client.post("/api/verify/screenshot", files=upload(PNG_BYTES))

    assert gemini.analyze_claim.await_args.kwargs["requested_language"] == "auto"


def test_image_with_no_claim_skips_research_honestly(client: TestClient) -> None:
    gemini, firecrawl = install_screenshot(
        extract_result=make_extraction(
            primary_claim="",
            has_factual_claim=False,
            extracted_text="just a cat photo",
            notes="This image is a photograph with no factual claim.",
            visible_date=None,
            visible_source=None,
        )
    )

    body = client.post("/api/verify/screenshot", files=upload(PNG_BYTES)).json()

    firecrawl.research.assert_not_awaited()
    gemini.analyze_claim.assert_not_awaited()
    assert body["verdict"] == "UNVERIFIED"
    assert body["confidence_score"] == 0.0
    assert body["sources"] == []
    assert body["important_context"]
    assert body["meta"]["degraded"] is True


def test_claim_flag_without_claim_text_is_treated_as_no_claim(client: TestClient) -> None:
    """Guards against a model setting the flag but returning nothing to check."""
    extraction = ScreenshotExtraction.from_payload(
        GeminiScreenshotPayload(
            extracted_text="some text",
            primary_claim="   ",
            language=DetectedLanguage.ENGLISH,
            kind=ScreenshotKind.OTHER,
            has_factual_claim=True,
        )
    )
    assert extraction.has_factual_claim is False


def test_one_word_extraction_does_not_crash_the_pipeline(client: TestClient) -> None:
    _, firecrawl = install_screenshot(
        extract_result=make_extraction(primary_claim="Hi", has_factual_claim=True)
    )

    response = client.post("/api/verify/screenshot", files=upload(PNG_BYTES))

    assert response.status_code == 200
    assert response.json()["verdict"] == "UNVERIFIED"
    firecrawl.research.assert_not_awaited()


def test_long_extracted_claim_still_fits_the_request_model(client: TestClient) -> None:
    """The extracted claim is fed back through VerifyRequest, so it must fit."""
    install_screenshot(extract_result=make_extraction(primary_claim="ক" * 4000))

    response = client.post("/api/verify/screenshot", files=upload(PNG_BYTES))

    assert response.status_code == 200


def test_bangla_text_survives_the_whole_workflow(client: TestClient) -> None:
    install_screenshot()
    body = client.post("/api/verify/screenshot", files=upload(PNG_BYTES)).json()

    assert "ঢাকায়" in body["extraction"]["primary_claim"]
    assert "প্রথম আলো" == body["extraction"]["visible_source"]


def test_no_api_keys_in_the_screenshot_response(client: TestClient) -> None:
    install_screenshot()
    raw = client.post("/api/verify/screenshot", files=upload(PNG_BYTES)).text.lower()

    for forbidden in ("api_key", "sk_", "fc-", "aiza"):
        assert forbidden not in raw


# --- upload failures --------------------------------------------------------


@pytest.mark.parametrize("endpoint", ["/api/screenshot/extract", "/api/verify/screenshot"])
def test_non_image_upload_returns_415(client: TestClient, endpoint: str) -> None:
    install_screenshot()
    response = client.post(endpoint, files=upload(PDF_BYTES, "doc.pdf", "application/pdf"))

    assert response.status_code == 415
    assert response.json()["error"] == "unsupported_media_type"


@pytest.mark.parametrize("endpoint", ["/api/screenshot/extract", "/api/verify/screenshot"])
def test_oversize_upload_returns_413(client: TestClient, endpoint: str) -> None:
    install_screenshot()
    huge = PNG_BYTES + b"\x00" * (6 * 1024 * 1024)

    response = client.post(endpoint, files=upload(huge))

    assert response.status_code == 413
    assert response.json()["error"] == "payload_too_large"
    assert "MB" in response.json()["message"]


def test_oversize_upload_is_never_sent_upstream(client: TestClient) -> None:
    gemini, _ = install_screenshot()
    huge = PNG_BYTES + b"\x00" * (6 * 1024 * 1024)

    client.post("/api/verify/screenshot", files=upload(huge))

    gemini.extract_claim_from_image.assert_not_awaited()


def test_truncated_image_returns_415(client: TestClient) -> None:
    install_screenshot()
    response = client.post("/api/verify/screenshot", files=upload(b"\x89PNG"))

    assert response.status_code == 415


def test_missing_file_returns_422(client: TestClient) -> None:
    install_screenshot()
    response = client.post("/api/verify/screenshot")

    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"


def test_missing_api_key_returns_503(client: TestClient) -> None:
    install_screenshot(
        extract_result=ServiceUnavailableError("GEMINI_API_KEY is not configured.")
    )
    response = client.post("/api/verify/screenshot", files=upload(PNG_BYTES))

    assert response.status_code == 503


def test_rate_limit_returns_429(client: TestClient) -> None:
    install_screenshot(extract_result=RateLimitError("Rate limit reached. Please wait."))
    response = client.post("/api/verify/screenshot", files=upload(PNG_BYTES))

    assert response.status_code == 429
    assert response.json()["error"] == "rate_limited"


def test_unreadable_image_returns_502(client: TestClient) -> None:
    install_screenshot(extract_result=ServiceError("The image could not be read properly."))
    response = client.post("/api/verify/screenshot", files=upload(PNG_BYTES))

    assert response.status_code == 502
    assert response.json()["error"] == "service_error"


# --- text verification must keep working ------------------------------------


def test_text_verification_is_unaffected(client: TestClient) -> None:
    """Adding the image path must not change the typed-claim contract."""
    install(
        claim_result=make_claim_analysis(),
        research_result=make_bundle(),
        evidence_result=make_evidence_analysis(),
    )

    response = client.post("/api/verify", json={"claim": "Bangladesh won in 2017."})

    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "LIKELY_FALSE"
    # No screenshot fields leak into a text verification.
    assert "extraction" not in body


def test_screenshot_and_text_share_one_verdict_system() -> None:
    """Any second verdict system would be a maintenance and consistency trap."""
    from app.models.verify import ScreenshotVerifyResponse, VerifyResponse

    assert issubclass(ScreenshotVerifyResponse, VerifyResponse)
    # Verdict-bearing fields are inherited, not redeclared.
    for field in ("verdict", "confidence_score", "explanation", "sources"):
        assert field not in ScreenshotVerifyResponse.__annotations__


def test_gemini_service_sends_image_and_prompt_together() -> None:
    """Unit-level check that the vision call is shaped correctly."""
    from app.config import Settings
    from app.services.gemini import GeminiService

    settings = Settings(gemini_api_key="test-key", firecrawl_api_key=None)
    service = GeminiService(settings)
    payload = GeminiScreenshotPayload(
        extracted_text="text",
        primary_claim="A claim about something.",
        language=DetectedLanguage.ENGLISH,
        kind=ScreenshotKind.NEWS_CARD,
        has_factual_claim=True,
    )
    mock = AsyncMock(return_value=SimpleNamespace(parsed=payload, text=None))

    async def run():
        with patch("google.genai.models.AsyncModels.generate_content", mock):
            result = await service.extract_claim_from_image(PNG_BYTES, "image/png")
        await service.aclose()
        return result

    import asyncio

    result = asyncio.run(run())

    contents = mock.await_args.kwargs["contents"]
    assert len(contents) == 2
    assert contents[0].inline_data.mime_type == "image/png"
    assert contents[0].inline_data.data == PNG_BYTES
    assert "Do not judge whether the claim is true" in contents[1]
    system = mock.await_args.kwargs["config"].system_instruction
    # Substrings kept short so prompt line wrapping does not break the assertion.
    assert "You do NOT decide whether" in system
    assert "cannot tell whether a screenshot has been edited" in system
    assert result.primary_claim == "A claim about something."
