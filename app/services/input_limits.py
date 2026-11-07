"""
Request-size enforcement and safe decoding of client-supplied binary data.

* `BodySizeLimitMiddleware` rejects oversized request bodies early (Content-Length) and
  also while streaming (chunked bodies with no/false Content-Length).
* `decode_image_b64` bounds base64 length, decoded bytes and image dimensions
  (decompression-bomb defence) BEFORE the image reaches OpenCV / Tesseract.
"""
import base64
import binascii
import io
from typing import Optional

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from app.config import settings

ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG", "GIF", "BMP", "WEBP"}


def max_b64_chars() -> int:
    return (settings.MAX_IMAGE_BYTES * 4) // 3 + 8


def decode_image_b64(data: Optional[str]) -> Optional[bytes]:
    """Strictly decode + validate a base64 image. Returns None when `data` is empty."""
    if not data:
        return None
    if len(data) > max_b64_chars():
        raise HTTPException(status_code=413, detail="Image payload exceeds the maximum permitted size.")
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="image_base64 is not valid base64.")
    validate_image_bytes(raw)
    return raw


def validate_image_bytes(raw: bytes) -> tuple[int, int]:
    """Verify bytes are a supported image of bounded dimensions; returns (width, height)."""
    if len(raw) > settings.MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds the maximum permitted size.")
    try:
        # Image.open reads only the header; dimensions are checked before any pixel decode.
        with Image.open(io.BytesIO(raw)) as img:
            fmt = (img.format or "").upper()
            width, height = img.size
            if fmt not in ALLOWED_IMAGE_FORMATS:
                raise HTTPException(status_code=400, detail="Unsupported image format.")
            if width * height > settings.MAX_IMAGE_PIXELS or width < 1 or height < 1:
                raise HTTPException(
                    status_code=413,
                    detail=f"Image dimensions exceed the permitted limit of {settings.MAX_IMAGE_PIXELS} pixels.",
                )
            img.verify()
            return width, height
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(status_code=400, detail="Payload is not a valid image.")


class BodySizeLimitMiddleware:
    """Pure-ASGI body size limiter (works for chunked uploads too)."""

    def __init__(self, app):
        self.app = app

    def _limit_for(self, headers: dict) -> int:
        content_type = headers.get(b"content-type", b"").decode("latin-1").lower()
        if content_type.startswith("multipart/form-data"):
            return settings.MAX_CSV_SIZE_BYTES + 64 * 1024  # file cap + multipart framing
        return settings.MAX_JSON_BODY_BYTES

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            return await self.app(scope, receive, send)

        headers = dict(scope.get("headers") or [])
        limit = self._limit_for(headers)

        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                if int(declared) > limit:
                    return await self._reject(send, limit)
            except ValueError:
                return await self._reject(send, limit, status=400, detail="Invalid Content-Length.")

        received = 0
        exceeded = False
        response_started = False
        replaced = False

        async def limited_receive():
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise _BodyTooLarge()
            return message

        async def tracking_send(message):
            nonlocal response_started, replaced
            if exceeded:
                # The framework may have turned our abort into a 400 while parsing the body;
                # the client must always see 413 for an oversized request.
                if not replaced and not response_started:
                    replaced = True
                    await self._reject(send, limit)
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if not response_started and not replaced:
                await self._reject(send, limit)

    @staticmethod
    async def _reject(send, limit: int, status: int = 413, detail: Optional[str] = None):
        import json as _json
        body = _json.dumps(
            {"detail": detail or f"Request body exceeds the maximum permitted size of {limit} bytes."}
        ).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})


class _BodyTooLarge(Exception):
    pass
