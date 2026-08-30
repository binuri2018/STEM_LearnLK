"""Image validation and preprocessing for Member 4 OCR."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

from backend.components.knowledge_maps.schemas import OcrPreprocessingInfo


MAX_IMAGE_BYTES = 10 * 1024 * 1024

_MIME_TO_FORMAT = {
    "image/jpeg": "JPEG",
    "image/jpg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
    "image/gif": "GIF",
}

ALLOWED_MIME = set(_MIME_TO_FORMAT)

_FORMAT_TO_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}


@dataclass(frozen=True)
class PreparedOcrImage:
    data: bytes
    mime: str
    preprocessing: OcrPreprocessingInfo


def _normalise_mime(mime: str | None) -> str:
    return (mime or "").split(";")[0].strip().lower()


def _open_validated_image(image_bytes: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            img.verify()
        return Image.open(BytesIO(image_bytes))
    except Image.DecompressionBombError as exc:
        raise ValueError("Image is too large to process safely") from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Invalid or corrupted image upload") from exc


def prepare_image_for_ocr(
    image_bytes: bytes,
    content_type: str | None,
    max_dimension: int,
) -> PreparedOcrImage:
    """Validate image bytes and return a provider-safe processed image."""
    if not image_bytes:
        raise ValueError("Empty image upload")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError(f"Image too large: {len(image_bytes)} bytes (max {MAX_IMAGE_BYTES})")

    claimed_mime = _normalise_mime(content_type)
    if claimed_mime not in _MIME_TO_FORMAT:
        raise ValueError(f"Unsupported image type: {claimed_mime!r}")

    img = _open_validated_image(image_bytes)
    try:
        detected_format = (img.format or "").upper()
        if detected_format not in _FORMAT_TO_MIME:
            raise ValueError(f"Unsupported image format: {detected_format!r}")
        if _MIME_TO_FORMAT[claimed_mime] != detected_format:
            raise ValueError("Image content does not match declared MIME type")

        preprocessing = OcrPreprocessingInfo(orientation_corrected=True)
        if detected_format == "GIF":
            img = next(ImageSequence.Iterator(img)).copy()
            output_format = "PNG"
        else:
            img = img.copy()
            output_format = "JPEG" if detected_format == "JPEG" else "PNG"

        img = ImageOps.exif_transpose(img).convert("RGB")
        try:
            img = ImageOps.autocontrast(img, cutoff=1)
            preprocessing.contrast_enhanced = True
        except Exception:
            preprocessing.contrast_enhanced = False

        safe_max = max(1, int(max_dimension or 2400))
        if max(img.size) > safe_max:
            img.thumbnail((safe_max, safe_max), Image.Resampling.LANCZOS)

        buf = BytesIO()
        save_kwargs = {"format": output_format}
        if output_format == "JPEG":
            save_kwargs["quality"] = 92
        img.save(buf, **save_kwargs)
        return PreparedOcrImage(
            data=buf.getvalue(),
            mime="image/jpeg" if output_format == "JPEG" else "image/png",
            preprocessing=preprocessing,
        )
    finally:
        try:
            img.close()
        except Exception:
            pass
