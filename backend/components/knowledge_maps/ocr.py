"""OCR for handwritten or printed images through the selected vision LLM.

Single public function: extract_text(image_bytes, mime_type) -> str.
Used by POST /api/m4/upload-ocr (and the legacy /api/upload-ocr alias).
"""
from __future__ import annotations

import base64

from backend.common.config import settings
from backend.components.knowledge_maps import llm_client
from backend.components.knowledge_maps.ocr_image import ALLOWED_MIME, MAX_IMAGE_BYTES, prepare_image_for_ocr
from backend.components.knowledge_maps.prompts import OCR_PROMPT


def _normalise_mime(mime: str | None) -> str:
    """Map browser-sent MIME strings to provider-compatible ones."""
    m = (mime or "").lower().strip()
    if m == "image/jpg":
        return "image/jpeg"
    return m or "image/jpeg"


def extract_text(image_bytes: bytes, mime_type: str | None = None) -> str:
    """Extract text from an image. Raises ValueError / RuntimeError on failure.

    - ValueError: bad input (size, mime). Caller maps to HTTP 400 / 413.
    - RuntimeError: provider not configured or returned no text.
    """
    mime = _normalise_mime(mime_type)
    if mime not in ALLOWED_MIME:
        raise ValueError(f"Unsupported image type: {mime!r}")

    prepared = prepare_image_for_ocr(image_bytes, mime, settings.m4_ocr_max_dimension)
    image_b64 = base64.b64encode(prepared.data).decode("ascii")
    text = llm_client.vision_extract(OCR_PROMPT, image_b64, mime=prepared.mime)
    text = (text or "").strip()
    if not text:
        raise RuntimeError("OCR returned no text — image may be blank or illegible")
    return text
