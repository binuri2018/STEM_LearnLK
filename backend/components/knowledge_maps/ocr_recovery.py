"""Advisory OCR recovery suggestions for science text."""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.components.knowledge_maps.schemas import OcrReviewItem

log = logging.getLogger(__name__)

_FORMULA_SUGGESTIONS = {
    "C02": ("CO₂", "Possible scientific-notation confusion between letter O and digit 0."),
    "H20": ("H₂O", "Possible scientific-notation confusion between letter O and digit 0."),
}

_CATEGORY_DEFAULT = "unclear"
_VALID_CATEGORIES = {"formula", "terminology", "spelling", "unclear"}


@dataclass(frozen=True)
class OcrGlossaryEntry:
    observed: str
    suggested: str
    category: str
    reason: str


def _normalise(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def load_ocr_glossary(path: str | None) -> list[OcrGlossaryEntry]:
    if not path:
        return []
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Could not load M4 OCR glossary: %s", exc)
        return []
    if not isinstance(raw, list):
        log.warning("M4 OCR glossary must be a JSON list")
        return []
    entries: list[OcrGlossaryEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        observed = str(item.get("observed") or "").strip()
        suggested = str(item.get("suggested") or "").strip()
        if not observed or not suggested:
            continue
        category = str(item.get("category") or "terminology")
        if category not in _VALID_CATEGORIES:
            category = "terminology"
        reason = str(item.get("reason") or "Curated glossary suggestion.")
        entries.append(OcrGlossaryEntry(observed, suggested, category, reason))
    return entries


def _find_normalised_exact(text: str, needle: str) -> list[tuple[int, int]]:
    # Exact matching on original text preserves Unicode offsets while the
    # comparison side uses NFKC/casefold rules for glossary robustness.
    matches: list[tuple[int, int]] = []
    norm_needle = _normalise(needle)
    for match in re.finditer(re.escape(needle), text, flags=re.IGNORECASE):
        if _normalise(match.group(0)) == norm_needle:
            matches.append((match.start(), match.end()))
    return matches


def _valid_model_item(text: str, item: dict[str, Any]) -> OcrReviewItem | None:
    try:
        start = int(item.get("start"))
        end = int(item.get("end"))
    except Exception:
        return None
    if start < 0 or end <= start or end > len(text):
        return None
    source_text = str(item.get("source_text") or text[start:end])
    if text[start:end] != source_text:
        return None
    suggested = str(item.get("suggested_text") or "").strip()
    if not suggested or suggested == source_text:
        return None
    category = str(item.get("category") or _CATEGORY_DEFAULT)
    if category not in _VALID_CATEGORIES:
        category = _CATEGORY_DEFAULT
    confidence = item.get("confidence")
    try:
        parsed_confidence = float(confidence) if confidence is not None else None
    except Exception:
        parsed_confidence = None
    return OcrReviewItem(
        review_id="Q0",
        source_text=source_text,
        suggested_text=suggested,
        reason=str(item.get("reason") or "OCR uncertainty reported by the vision model."),
        start=start,
        end=end,
        confidence=parsed_confidence,
        category=category,  # type: ignore[arg-type]
    )


def _overlaps(a: OcrReviewItem, b: OcrReviewItem) -> bool:
    return max(a.start, b.start) < min(a.end, b.end)


def build_review_items(
    text: str,
    model_items: list[dict[str, Any]],
    glossary_path: str | None = None,
) -> list[OcrReviewItem]:
    candidates: list[tuple[int, OcrReviewItem]] = []

    for entry in load_ocr_glossary(glossary_path):
        for start, end in _find_normalised_exact(text, entry.observed):
            candidates.append(
                (
                    0,
                    OcrReviewItem(
                        review_id="Q0",
                        source_text=text[start:end],
                        suggested_text=entry.suggested,
                        reason=entry.reason,
                        start=start,
                        end=end,
                        confidence=None,
                        category=entry.category,  # type: ignore[arg-type]
                    ),
                )
            )

    for token, (suggested, reason) in _FORMULA_SUGGESTIONS.items():
        for match in re.finditer(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])", text):
            candidates.append(
                (
                    1,
                    OcrReviewItem(
                        review_id="Q0",
                        source_text=match.group(0),
                        suggested_text=suggested,
                        reason=reason,
                        start=match.start(),
                        end=match.end(),
                        confidence=None,
                        category="formula",
                    ),
                )
            )

    for item in model_items:
        parsed = _valid_model_item(text, item)
        if parsed is not None:
            candidates.append((2, parsed))

    selected: list[tuple[int, OcrReviewItem]] = []
    for priority, item in sorted(candidates, key=lambda pair: (pair[0], pair[1].start, pair[1].end)):
        if any(_overlaps(item, existing) for _, existing in selected):
            continue
        selected.append((priority, item))

    output: list[OcrReviewItem] = []
    for index, (_, item) in enumerate(sorted(selected, key=lambda pair: (pair[1].start, pair[1].end)), start=1):
        item.review_id = f"Q{index}"
        output.append(item)
    return output
