"""Upload validation for screenshots.

The client's declared content type is a hint, not a fact: it is trivially spoofed and
often simply wrong (Android share sheets mislabel files routinely). So the real
format is sniffed from the file's own magic bytes, and that is what gets sent to
Gemini. A PDF renamed to .png is rejected here rather than confusing the model.
"""

import logging

from app.utils.errors import (
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)

logger = logging.getLogger(__name__)

# Formats Gemini accepts and that people actually screenshot with.
PNG = "image/png"
JPEG = "image/jpeg"
WEBP = "image/webp"
GIF = "image/gif"

SUPPORTED_MIME_TYPES = frozenset({PNG, JPEG, WEBP, GIF})
SUPPORTED_LABEL = "PNG, JPEG, WebP, or GIF"

# Smallest plausible screenshot. Below this it is a tracking pixel or a truncated
# upload, not an image with a readable claim in it.
MIN_IMAGE_BYTES = 100


def sniff_image_mime(data: bytes) -> str | None:
    """Detect the image type from magic bytes. None when it is not a known image."""
    if len(data) < 12:
        return None

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return WEBP
    if data.startswith((b"GIF87a", b"GIF89a")):
        return GIF
    return None


def validate_image(
    data: bytes,
    declared_mime: str | None,
    max_bytes: int,
) -> str:
    """Validate an uploaded screenshot and return its true MIME type.

    Raises:
        PayloadTooLargeError: the file exceeds the configured limit.
        UnsupportedMediaTypeError: empty, truncated, or not a supported image.
    """
    if len(data) > max_bytes:
        raise PayloadTooLargeError(
            f"That image is too large. Please upload a file under "
            f"{max_bytes // (1024 * 1024)} MB.",
            details={"size_bytes": len(data), "max_bytes": max_bytes},
        )

    if not data:
        raise UnsupportedMediaTypeError("No image data was received. Please try again.")

    if len(data) < MIN_IMAGE_BYTES:
        raise UnsupportedMediaTypeError(
            "That file is too small to be a readable screenshot."
        )

    actual_mime = sniff_image_mime(data)
    if actual_mime is None:
        raise UnsupportedMediaTypeError(
            f"That file is not a supported image. Please upload a {SUPPORTED_LABEL} file."
        )

    if declared_mime and declared_mime.split(";")[0].strip().lower() != actual_mime:
        # Not an error: the sniffed type wins and the upload proceeds.
        logger.info(
            "upload declared %s but is actually %s; using the detected type",
            declared_mime,
            actual_mime,
        )

    return actual_mime
