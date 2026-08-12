"""Small standard-library validation for bounded PNG/JPEG evidence."""

from __future__ import annotations

import struct


MAX_IMAGE_DIMENSION = 16_384
MAX_IMAGE_PIXELS = 50_000_000
_JPEG_SOF_MARKERS = {
    0xC0,
    0xC1,
    0xC2,
    0xC3,
    0xC5,
    0xC6,
    0xC7,
    0xC9,
    0xCA,
    0xCB,
    0xCD,
    0xCE,
    0xCF,
}


class ImageValidationError(ValueError):
    """Raised when image bytes are malformed or unsafe to hand to an image decoder."""


def _validate_dimensions(width: int, height: int) -> None:
    if (
        width < 1
        or height < 1
        or width > MAX_IMAGE_DIMENSION
        or height > MAX_IMAGE_DIMENSION
        or width * height > MAX_IMAGE_PIXELS
    ):
        raise ImageValidationError("image dimensions exceed the safe limit")


def _validate_png(body: bytes) -> str:
    if len(body) < 33 or body[8:12] != b"\x00\x00\x00\r" or body[12:16] != b"IHDR":
        raise ImageValidationError("PNG header is invalid")
    width, height = struct.unpack(">II", body[16:24])
    _validate_dimensions(width, height)
    return "image/png"


def _validate_jpeg(body: bytes) -> str:
    if len(body) < 12 or not body.endswith(b"\xff\xd9"):
        raise ImageValidationError("JPEG framing is invalid")
    offset = 2
    while offset + 1 < len(body):
        if body[offset] != 0xFF:
            raise ImageValidationError("JPEG marker stream is invalid")
        while offset < len(body) and body[offset] == 0xFF:
            offset += 1
        if offset >= len(body):
            break
        marker = body[offset]
        offset += 1
        if marker == 0xD9:
            break
        if marker == 0xDA:
            break
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:
            continue
        if offset + 2 > len(body):
            raise ImageValidationError("JPEG segment is truncated")
        segment_length = int.from_bytes(body[offset : offset + 2], "big")
        if segment_length < 2 or offset + segment_length > len(body):
            raise ImageValidationError("JPEG segment length is invalid")
        if marker in _JPEG_SOF_MARKERS:
            if segment_length < 7:
                raise ImageValidationError("JPEG frame header is invalid")
            height = int.from_bytes(body[offset + 3 : offset + 5], "big")
            width = int.from_bytes(body[offset + 5 : offset + 7], "big")
            _validate_dimensions(width, height)
            return "image/jpeg"
        offset += segment_length
    raise ImageValidationError("JPEG dimensions are missing")


def validate_image_bytes(body: bytes) -> str:
    """Return the canonical media type after structural and dimension validation."""

    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return _validate_png(body)
    if body.startswith(b"\xff\xd8"):
        return _validate_jpeg(body)
    raise ImageValidationError("image signature is unsupported")
