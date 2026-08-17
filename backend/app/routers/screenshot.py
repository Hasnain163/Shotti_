"""Screenshot verification endpoints.

Two endpoints, because reading an image and verifying a claim have very different
costs:

* ``POST /api/screenshot/extract`` — one Gemini call. Returns what was read so the
  user can confirm or correct it. Verifying a misread claim produces a confident
  answer to the wrong question, which is worse than asking.
* ``POST /api/verify/screenshot`` — read, then run the ordinary verification
  pipeline. One request, for clients that would rather skip the confirmation step.

Both share the same validation and the same verdict system.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.config import Settings, get_settings
from app.dependencies import get_gemini_service, get_pipeline
from app.models.verify import ScreenshotExtractionResponse, ScreenshotVerifyResponse
from app.services.gemini import GeminiService
from app.services.pipeline import VerificationPipeline
from app.utils.errors import ErrorResponse, PayloadTooLargeError
from app.utils.images import SUPPORTED_LABEL, validate_image

logger = logging.getLogger(__name__)

router = APIRouter(tags=["screenshot"])

_UPLOAD_ERRORS = {
    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: {"model": ErrorResponse},
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"model": ErrorResponse},
    status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
    status.HTTP_502_BAD_GATEWAY: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}

_CHUNK_SIZE = 64 * 1024


async def read_upload(image: UploadFile, max_bytes: int) -> bytes:
    """Read an upload, refusing to buffer more than the limit allows.

    Reading in chunks and stopping one byte over the limit means an oversized or
    hostile upload cannot be pulled into memory whole just to be rejected.
    """
    chunks: list[bytes] = []
    total = 0

    while chunk := await image.read(_CHUNK_SIZE):
        total += len(chunk)
        if total > max_bytes:
            logger.info("rejected upload over %d bytes", max_bytes)
            raise PayloadTooLargeError(
                f"That image is too large. Please upload a file under "
                f"{max_bytes // (1024 * 1024)} MB.",
                details={"max_bytes": max_bytes},
            )
        chunks.append(chunk)

    return b"".join(chunks)


async def _validated_image(image: UploadFile, settings: Settings) -> tuple[bytes, str]:
    data = await read_upload(image, settings.screenshot_max_bytes)
    mime_type = validate_image(
        data=data,
        declared_mime=image.content_type,
        max_bytes=settings.screenshot_max_bytes,
    )
    logger.info(
        "screenshot accepted: %s, %d bytes, filename=%r",
        mime_type,
        len(data),
        image.filename,
    )
    return data, mime_type


@router.post(
    "/screenshot/extract",
    response_model=ScreenshotExtractionResponse,
    summary="Read a screenshot and return the claim it contains",
    description=(
        "Extracts text, the central claim, and any visible date or source. "
        f"Accepts {SUPPORTED_LABEL}. Performs no research and returns no verdict."
    ),
    responses=_UPLOAD_ERRORS,
)
async def extract_screenshot(
    settings: Annotated[Settings, Depends(get_settings)],
    gemini: Annotated[GeminiService, Depends(get_gemini_service)],
    image: Annotated[UploadFile, File(description="Screenshot to read.")],
) -> ScreenshotExtractionResponse:
    data, mime_type = await _validated_image(image, settings)
    extraction = await gemini.extract_claim_from_image(image_bytes=data, mime_type=mime_type)
    return ScreenshotExtractionResponse(
        extraction=extraction,
        suggested_claim=extraction.primary_claim,
    )


@router.post(
    "/verify/screenshot",
    response_model=ScreenshotVerifyResponse,
    summary="Verify the claim inside a screenshot",
    description=(
        "Reads the image, then runs the same verification pipeline used for typed "
        f"claims. Accepts {SUPPORTED_LABEL}."
    ),
    responses=_UPLOAD_ERRORS,
)
async def verify_screenshot(
    settings: Annotated[Settings, Depends(get_settings)],
    pipeline: Annotated[VerificationPipeline, Depends(get_pipeline)],
    image: Annotated[UploadFile, File(description="Screenshot to verify.")],
) -> ScreenshotVerifyResponse:
    data, mime_type = await _validated_image(image, settings)
    return await pipeline.verify_screenshot(image_bytes=data, mime_type=mime_type)
