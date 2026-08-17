"""Shotti? AI — FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.dependencies import close_services
from app.routers import health, verify
from app.utils.errors import ErrorResponse, ShottiError

settings = get_settings()

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Close upstream HTTP clients on shutdown."""
    yield
    await close_services()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Bangla/English misinformation verification API.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ShottiError)
async def handle_shotti_error(_: Request, exc: ShottiError) -> JSONResponse:
    """Expected application errors — logged as warnings, message shown to the user."""
    logger.warning("%s: %s", exc.error_code, exc.message)
    body = ErrorResponse(error=exc.error_code, message=exc.message, details=exc.details)
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Bad request bodies get the same envelope as every other error."""
    body = ErrorResponse(
        error="validation_error",
        message="The request body is invalid. Check the highlighted fields.",
        details={"errors": exc.errors()},
    )
    # Validation errors can hold non-JSON values (e.g. a raw ValueError), so encode.
    return JSONResponse(status_code=422, content=jsonable_encoder(body))


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    """404s and other HTTP errors, in the shared envelope."""
    body = ErrorResponse(error="http_error", message=str(exc.detail))
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


@app.exception_handler(Exception)
async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    """Last resort: log the real cause, return a generic message (never a stack trace)."""
    logger.exception("unhandled error: %s", exc)
    body = ErrorResponse(
        error="internal_error",
        message="Something went wrong on our side. Please try again.",
    )
    return JSONResponse(status_code=500, content=body.model_dump())


app.include_router(health.router, prefix="/api")
app.include_router(verify.router, prefix="/api")


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"app": settings.app_name, "docs": "/docs", "health": "/api/health"}
