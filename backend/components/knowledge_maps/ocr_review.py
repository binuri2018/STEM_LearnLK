"""Structured OCR review flow for Member 4."""
from __future__ import annotations

import base64
import json
from typing import Any

from backend.common.config import settings
from backend.components.knowledge_maps import llm_client
from backend.components.knowledge_maps.ocr_image import prepare_image_for_ocr
from backend.components.knowledge_maps.ocr_recovery import build_review_items
from backend.components.knowledge_maps.prompts import OCR_REVIEW_PROMPT
from backend.components.knowledge_maps.schemas import OcrRegion, OcrReviewResponse


def _confidence_band(confidences: list[float]) -> str:
    if not confidences:
        return "unavailable"
    mean_confidence = sum(confidences) / len(confidences)
    if mean_confidence >= settings.m4_ocr_confidence_high:
        return "high"
    if mean_confidence >= settings.m4_ocr_confidence_low:
        return "medium"
    return "low"


def _parse_json_response(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _valid_regions(text: str, raw_regions: Any) -> list[OcrRegion]:
    regions: list[OcrRegion] = []
    if not isinstance(raw_regions, list):
        raw_regions = []
    for index, item in enumerate(raw_regions, start=1):
        if not isinstance(item, dict):
            continue
        region_text = str(item.get("text") or "").strip()
        if not region_text:
            continue
        region_type = str(item.get("region_type") or "paragraph")
        if region_type not in {"paragraph", "table", "equation", "label", "diagram"}:
            region_type = "paragraph"
        confidence = item.get("confidence")
        try:
            parsed_confidence = float(confidence) if confidence is not None else None
        except Exception:
            parsed_confidence = None
        warnings = item.get("warnings")
        if not isinstance(warnings, list):
            warnings = []
        regions.append(
            OcrRegion(
                region_id=str(item.get("region_id") or f"R{index}"),
                region_type=region_type,  # type: ignore[arg-type]
                text=region_text,
                confidence=parsed_confidence,
                reading_order=int(item.get("reading_order") or index),
                warnings=[str(w) for w in warnings if str(w).strip()],
            )
        )
    if regions:
        return sorted(regions, key=lambda region: region.reading_order)
    return [OcrRegion(region_id="R1", region_type="paragraph", text=text, reading_order=1)]


def review_image(image_bytes: bytes, mime_type: str | None = None) -> OcrReviewResponse:
    prepared = prepare_image_for_ocr(image_bytes, mime_type, settings.m4_ocr_max_dimension)
    image_b64 = base64.b64encode(prepared.data).decode("ascii")
    raw = llm_client.vision_extract(OCR_REVIEW_PROMPT, image_b64, mime=prepared.mime)
    raw = (raw or "").strip()
    if not raw:
        raise RuntimeError("OCR returned no text — image may be blank or illegible")

    parsed = _parse_json_response(raw)
    if parsed is None:
        text = raw
        return OcrReviewResponse(
            text=text,
            review_status="needs_review",
            overall_confidence="unavailable",
            regions=[OcrRegion(region_id="R1", region_type="paragraph", text=text, reading_order=1)],
            review_items=build_review_items(text, [], settings.m4_ocr_glossary_path),
            preprocessing=prepared.preprocessing,
        )

    text = str(parsed.get("text") or "").strip()
    if not text:
        raise RuntimeError("OCR returned no text — image may be blank or illegible")
    regions = _valid_regions(text, parsed.get("regions"))
    confidences = [r.confidence for r in regions if r.confidence is not None]
    model_items = parsed.get("uncertain_spans")
    if not isinstance(model_items, list):
        model_items = []
    review_items = build_review_items(text, model_items, settings.m4_ocr_glossary_path)
    band = _confidence_band(confidences)
    return OcrReviewResponse(
        text=text,
        review_status="needs_review" if review_items or band in {"low", "medium", "unavailable"} else "ready",
        overall_confidence=band,  # type: ignore[arg-type]
        regions=regions,
        review_items=review_items,
        preprocessing=prepared.preprocessing,
    )
