from __future__ import annotations

import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image


def image_bytes(fmt: str = "PNG", size: tuple[int, int] = (40, 30), color: str = "white") -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format=fmt)
    return buf.getvalue()


class OcrReviewSchemaTests(unittest.TestCase):
    def test_ocr_review_schema_preserves_sinhala_and_formula_suggestion(self):
        from backend.components.knowledge_maps.schemas import OcrReviewResponse

        payload = OcrReviewResponse(
            text="ප්‍රභා සංස්ලේෂණයට C02 අවශය වේ",
            review_status="needs_review",
            overall_confidence="low",
            regions=[
                {
                    "region_id": "R1",
                    "region_type": "paragraph",
                    "text": "ප්‍රභා සංස්ලේෂණයට C02 අවශය වේ",
                    "confidence": 0.68,
                    "reading_order": 1,
                    "warnings": ["mixed_language"],
                }
            ],
            review_items=[
                {
                    "review_id": "Q1",
                    "source_text": "C02",
                    "suggested_text": "CO₂",
                    "reason": "Possible scientific-notation confusion between letter O and digit 0.",
                    "start": 18,
                    "end": 21,
                    "confidence": 0.72,
                    "category": "formula",
                }
            ],
            preprocessing={
                "orientation_corrected": True,
                "contrast_enhanced": True,
                "margins_cropped": False,
            },
        )

        data = payload.model_dump()
        self.assertEqual(data["review_items"][0]["suggested_text"], "CO₂")
        self.assertEqual(
            data["retention"],
            "Image processed in memory and discarded after this request.",
        )

    def test_ocr_settings_defaults_exist(self):
        from backend.common.config import Settings

        settings = Settings()
        self.assertEqual(settings.m4_ocr_glossary_path, "")
        self.assertEqual(settings.m4_ocr_max_dimension, 2400)
        self.assertEqual(settings.m4_ocr_confidence_low, 0.65)
        self.assertEqual(settings.m4_ocr_confidence_high, 0.85)


class OcrImagePreparationTests(unittest.TestCase):
    def test_prepare_image_rejects_mime_signature_mismatch(self):
        from backend.components.knowledge_maps.ocr_image import prepare_image_for_ocr

        with self.assertRaises(ValueError):
            prepare_image_for_ocr(image_bytes("PNG"), "image/jpeg", max_dimension=2400)

    def test_prepare_image_resizes_and_keeps_safe_mime(self):
        from backend.components.knowledge_maps.ocr_image import prepare_image_for_ocr

        prepared = prepare_image_for_ocr(image_bytes("PNG", size=(3000, 1200)), "image/png", 2400)

        self.assertEqual(prepared.mime, "image/png")
        with Image.open(BytesIO(prepared.data)) as img:
            self.assertEqual(max(img.size), 2400)
        self.assertTrue(prepared.preprocessing.contrast_enhanced)

    def test_prepare_image_uses_first_gif_frame(self):
        from backend.components.knowledge_maps.ocr_image import prepare_image_for_ocr

        prepared = prepare_image_for_ocr(image_bytes("GIF"), "image/gif", 2400)

        self.assertEqual(prepared.mime, "image/png")


class OcrReviewServiceTests(unittest.TestCase):
    @patch("backend.components.knowledge_maps.llm_client.vision_extract")
    def test_review_image_parses_structured_json(self, mock_vision):
        from backend.components.knowledge_maps.ocr_review import review_image

        mock_vision.return_value = json.dumps(
            {
                "text": "Photosynthesis needs C02.",
                "regions": [
                    {
                        "region_id": "R1",
                        "region_type": "paragraph",
                        "text": "Photosynthesis needs C02.",
                        "confidence": 0.7,
                        "reading_order": 1,
                        "warnings": ["possible_formula_error"],
                    }
                ],
                "uncertain_spans": [
                    {
                        "source_text": "C02",
                        "suggested_text": "CO₂",
                        "reason": "Possible formula OCR confusion.",
                        "start": 21,
                        "end": 24,
                        "confidence": 0.7,
                        "category": "formula",
                    }
                ],
            }
        )

        result = review_image(image_bytes("PNG"), "image/png")

        self.assertEqual(result.text, "Photosynthesis needs C02.")
        self.assertEqual(result.review_status, "needs_review")
        self.assertEqual(result.overall_confidence, "medium")
        self.assertEqual(result.review_items[0].suggested_text, "CO₂")

    @patch("backend.components.knowledge_maps.llm_client.vision_extract")
    def test_review_image_falls_back_to_plain_text(self, mock_vision):
        from backend.components.knowledge_maps.ocr_review import review_image

        mock_vision.return_value = "plain සිංහල text"

        result = review_image(image_bytes("PNG"), "image/png")

        self.assertEqual(result.text, "plain සිංහල text")
        self.assertEqual(result.overall_confidence, "unavailable")
        self.assertEqual(result.regions[0].region_type, "paragraph")

    def test_formula_suggestions_are_advisory_and_offset_valid(self):
        from backend.components.knowledge_maps.ocr_recovery import build_review_items

        text = "C02 and H20 are written badly."
        items = build_review_items(text, [], None)

        self.assertEqual(
            [(i.source_text, i.suggested_text, text[i.start : i.end]) for i in items],
            [("C02", "CO₂", "C02"), ("H20", "H₂O", "H20")],
        )
        self.assertIn("C02", text)

    def test_glossary_exact_match_preferred_over_model_overlap(self):
        from backend.components.knowledge_maps.ocr_recovery import build_review_items

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "glossary.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "observed": "cloroplast",
                            "suggested": "chloroplast",
                            "category": "terminology",
                            "reason": "Common biology term spelling.",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            items = build_review_items(
                "cloroplast",
                [
                    {
                        "source_text": "cloroplast",
                        "suggested_text": "chlor plast",
                        "reason": "model",
                        "start": 0,
                        "end": 9,
                        "category": "spelling",
                    }
                ],
                str(path),
            )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].suggested_text, "chloroplast")


class OcrReviewRouteTests(unittest.TestCase):
    def test_ocr_review_endpoint_returns_review_response(self):
        from backend.main import app
        from backend.components.knowledge_maps.schemas import OcrReviewResponse

        client = TestClient(app)
        with patch("backend.components.knowledge_maps.router.run_ocr_review") as mock_review:
            mock_review.return_value = OcrReviewResponse(
                text="Photosynthesis needs C02.",
                review_status="needs_review",
                overall_confidence="medium",
                regions=[
                    {
                        "region_id": "R1",
                        "region_type": "paragraph",
                        "text": "Photosynthesis needs C02.",
                        "reading_order": 1,
                    }
                ],
                review_items=[],
            )
            response = client.post(
                "/api/m4/ocr-review",
                files={"file": ("note.png", image_bytes("PNG"), "image/png")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["review_status"], "needs_review")


if __name__ == "__main__":
    unittest.main()
