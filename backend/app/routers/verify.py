"""Claim verification endpoint.

HTTP concerns only: validate the request, hand it to the pipeline, let the shared
exception handlers turn errors into the standard envelope. No business logic here.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.dependencies import get_pipeline
from app.models.verify import VerifyRequest, VerifyResponse
from app.services.pipeline import VerificationPipeline
from app.utils.errors import ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["verify"])


@router.post(
    "/verify",
    response_model=VerifyResponse,
    summary="Verify a factual claim against web evidence",
    responses={
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorResponse},
        status.HTTP_502_BAD_GATEWAY: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
async def verify(
    payload: VerifyRequest,
    pipeline: Annotated[VerificationPipeline, Depends(get_pipeline)],
) -> VerifyResponse:
    return await pipeline.verify(payload)
