from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.components.knowledge_maps import schemas

try:
    from backend.components.knowledge_maps import evidence
except ImportError:
    evidence = None


class EvidenceSchemaTests(unittest.TestCase):
    def test_claim_keeps_existing_fields_and_defaults_to_unavailable_evidence(self) -> None:
        claim = schemas.Claim(
            claim="Cells respire.",
            verdict="correct",
            explanation="Supported.",
        )

        payload = claim.model_dump()

        self.assertEqual(payload["claim"], "Cells respire.")
        self.assertEqual(payload["source"], "syllabus")
        self.assertEqual(payload.get("evidence_status"), "unavailable")
        self.assertEqual(payload.get("evidence"), [])

    def test_evidence_item_serializes_exact_citation_fields(self) -> None:
        EvidenceItem = getattr(schemas, "EvidenceItem", None)
        self.assertIsNotNone(EvidenceItem, "EvidenceItem schema must exist")

        item = EvidenceItem(
            evidence_id="S2",
            source_type="syllabus",
            relation="supports",
            title="science Grade 10 Part 1",
            excerpt="Chloroplasts are the sites of photosynthesis.",
            url="/api/m4/documents/abc#page=47",
            document_id="abc",
            pdf_page_start=47,
            pdf_page_end=47,
            grade=10,
            topic="Science · Grade 10 · Part 1",
            subtopic="Part 1",
            document_type="Syllabus & learner material",
            retrieval_score=0.81,
        )

        self.assertEqual(item.model_dump()["pdf_page_start"], 47)
        self.assertEqual(item.model_dump()["source_type"], "syllabus")


class EvidenceModuleContractTests(unittest.TestCase):
    def test_evidence_helper_module_is_available(self) -> None:
        self.assertIsNotNone(evidence, "backend.components.knowledge_maps.evidence must be implemented")


class FrontendCachePolicyTests(unittest.TestCase):
    def test_student_ui_and_static_assets_must_be_revalidated(self) -> None:
        from fastapi.testclient import TestClient

        from backend.main import app

        with TestClient(app) as client:
            for path in ("/", "/static/knowledge_maps/app.js", "/static/knowledge_maps/styles.css"):
                with self.subTest(path=path):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("no-cache", response.headers.get("cache-control", ""))


@unittest.skipIf(evidence is None, "evidence helper module is not implemented")
class EvidenceHelperTests(unittest.TestCase):
    def test_document_id_is_stable_across_path_separator_styles(self) -> None:
        self.assertEqual(
            evidence.document_id_for_source("grade10/science.pdf"),
            evidence.document_id_for_source(r"grade10\science.pdf"),
        )

    def test_document_id_rejects_absolute_and_parent_paths(self) -> None:
        for unsafe in ("../secret.pdf", "/tmp/secret.pdf", r"..\secret.pdf"):
            with self.subTest(unsafe=unsafe):
                with self.assertRaises(ValueError):
                    evidence.document_id_for_source(unsafe)

    def test_document_resolution_allows_only_registered_pdfs_inside_resource(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "Resource"
            root.mkdir()
            book = root / "grade10" / "science.pdf"
            book.parent.mkdir()
            book.write_bytes(b"%PDF-1.4\n")
            text = root / "notes.txt"
            text.write_text("not a pdf", encoding="utf-8")

            book_id = evidence.document_id_for_source("grade10/science.pdf")
            text_id = evidence.document_id_for_source("notes.txt")

            self.assertEqual(evidence.resolve_document(book_id, root), book.resolve())
            self.assertIsNone(evidence.resolve_document(text_id, root))
            self.assertIsNone(evidence.resolve_document("unknown", root))

    def test_document_resolution_rejects_symlink_that_escapes_resource(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "Resource"
            root.mkdir()
            outside = base / "outside.pdf"
            outside.write_bytes(b"%PDF-1.4\n")
            link = root / "linked.pdf"
            try:
                link.symlink_to(outside)
            except OSError:
                self.skipTest("Symlinks require unprivileged developer mode on Windows")

            link_id = evidence.document_id_for_source("linked.pdf")

            self.assertIsNone(evidence.resolve_document(link_id, root))

    def test_selection_returns_only_valid_selected_hit_and_exact_chunk(self) -> None:
        hits = [
            {
                "evidence_id": "S1",
                "text": "General information about plant cells.",
                "score": 0.62,
                "source_file": "science Grade 10 Part 1.pdf",
                "page_start": 46,
                "page_end": 46,
                "grade": 10,
                "topic": "Science · Grade 10 · Part 1",
                "subtopic": "Part 1",
                "document_type": "Syllabus & learner material",
            },
            {
                "evidence_id": "S2",
                "text": "Chloroplasts are the sites of photosynthesis.",
                "score": 0.81,
                "source_file": "science Grade 10 Part 1.pdf",
                "page_start": 47,
                "page_end": 47,
                "grade": 10,
                "topic": "Science · Grade 10 · Part 1",
                "subtopic": "Part 1",
                "document_type": "Syllabus & learner material",
            },
        ]

        selected, status = evidence.select_syllabus_evidence(
            hits,
            ["S2", "S2", "missing"],
            "correct",
        )

        self.assertEqual(status, "cited")
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].evidence_id, "S2")
        self.assertEqual(selected[0].excerpt, hits[1]["text"])
        self.assertEqual(selected[0].relation, "supports")
        self.assertEqual(selected[0].pdf_page_start, 47)
        self.assertTrue(selected[0].url.endswith("#page=47"))

    def test_selection_distinguishes_no_hits_from_invalid_model_selection(self) -> None:
        selected, status = evidence.select_syllabus_evidence([], [], "correct")
        self.assertEqual(selected, [])
        self.assertEqual(status, "not_found")

        selected, status = evidence.select_syllabus_evidence(
            [{"evidence_id": "S1", "text": "Context", "source_file": "book.pdf"}],
            ["invalid"],
            "correct",
        )
        self.assertEqual(selected, [])
        self.assertEqual(status, "unavailable")


class VerificationEvidenceTests(unittest.TestCase):
    def _hits(self) -> list[dict]:
        return [
            {
                "score": 0.65,
                "text": "Plant cells contain several organelles.",
                "source_file": "science Grade 10 Part 1.pdf",
                "page_start": 46,
                "page_end": 46,
                "grade": 10,
                "topic": "Science · Grade 10 · Part 1",
                "subtopic": "Part 1",
                "document_type": "Syllabus & learner material",
            },
            {
                "score": 0.82,
                "text": "Chloroplasts are the sites of photosynthesis.",
                "source_file": "science Grade 10 Part 1.pdf",
                "page_start": 47,
                "page_end": 47,
                "grade": 10,
                "topic": "Science · Grade 10 · Part 1",
                "subtopic": "Part 1",
                "document_type": "Syllabus & learner material",
            },
        ]

    def test_verifier_returns_only_the_model_selected_syllabus_evidence(self) -> None:
        from backend.components.knowledge_maps import verification

        raw = {
            "verdict": "correct",
            "explanation": "The second passage directly supports the claim.",
            "evidence_ids": ["S2"],
        }
        with (
            patch.object(verification, "_extract_claims", return_value=["Photosynthesis occurs in chloroplasts."]),
            patch.object(verification, "retrieve", return_value=self._hits()),
            patch.object(verification.llm_client, "chat_with_tools", return_value=raw) as chat,
        ):
            result = verification.verify_text("student note", object(), "en")

        claim = result.claims[0]
        self.assertEqual(claim.evidence_status, "cited")
        self.assertEqual([item.evidence_id for item in claim.evidence], ["S2"])
        self.assertEqual(claim.evidence[0].excerpt, self._hits()[1]["text"])
        user_prompt = chat.call_args.kwargs["messages"][1]["content"]
        self.assertIn("[Evidence S1]", user_prompt)
        self.assertIn("[Evidence S2]", user_prompt)

    def test_verifier_marks_empty_retrieval_as_not_found(self) -> None:
        from backend.components.knowledge_maps import verification

        raw = {
            "verdict": "incomplete",
            "explanation": "No relevant syllabus context was found.",
            "evidence_ids": [],
        }
        with (
            patch.object(verification, "_extract_claims", return_value=["An out-of-syllabus claim."]),
            patch.object(verification, "retrieve", return_value=[]),
            patch.object(verification.llm_client, "chat_with_tools", return_value=raw),
        ):
            result = verification.verify_text("student note", object(), "en")

        self.assertEqual(result.claims[0].evidence_status, "not_found")
        self.assertEqual(result.claims[0].evidence, [])

    def test_verifier_does_not_substitute_for_an_invalid_evidence_id(self) -> None:
        from backend.components.knowledge_maps import verification

        raw = {
            "verdict": "correct",
            "explanation": "Supported.",
            "evidence_ids": ["S99"],
        }
        with (
            patch.object(verification, "_extract_claims", return_value=["A claim."]),
            patch.object(verification, "retrieve", return_value=self._hits()),
            patch.object(verification.llm_client, "chat_with_tools", return_value=raw),
        ):
            result = verification.verify_text("student note", object(), "en")

        self.assertEqual(result.claims[0].evidence_status, "unavailable")
        self.assertEqual(result.claims[0].evidence, [])


class WebEvidenceContractTests(unittest.TestCase):
    def test_web_search_exposes_structured_provenance_contract(self) -> None:
        from backend.components.knowledge_maps import web_search

        self.assertTrue(hasattr(web_search, "WebSearchResult"))
        self.assertTrue(hasattr(web_search, "WebCheckResult"))
        self.assertTrue(hasattr(web_search, "normalise_web_results"))


class WebEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        from backend.components.knowledge_maps import web_search

        required = ("WebSearchResult", "WebCheckResult", "normalise_web_results")
        if not all(hasattr(web_search, name) for name in required):
            self.skipTest("structured web provenance is not implemented")
        self.web_search = web_search

    def test_normalisation_keeps_only_http_sources_with_titles_and_snippets(self) -> None:
        results = self.web_search.normalise_web_results(
            [
                {"title": "Science source", "href": "https://science.example/fact", "body": "Evidence text"},
                {"title": "Unsafe", "href": "javascript:alert(1)", "body": "Bad"},
                {"title": "Missing host", "href": "https:///broken", "body": "Bad"},
            ]
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].evidence_id, "W1")
        self.assertEqual(results[0].domain, "science.example")
        self.assertEqual(results[0].snippet, "Evidence text")

    def test_web_judge_returns_only_selected_url_backed_evidence(self) -> None:
        results = self.web_search.normalise_web_results(
            [
                {"title": "First", "href": "https://one.example/fact", "body": "First snippet"},
                {"title": "Second", "href": "https://two.example/fact", "body": "Second snippet"},
            ]
        )
        raw = {"verdict": "correct", "evidence_ids": ["W2", "W2", "missing"]}
        with (
            patch.object(self.web_search, "_ddg_results", return_value=results),
            patch.object(self.web_search.llm_client, "chat_with_tools", return_value=raw),
        ):
            checked = self.web_search.judge_web_evidence(
                "A scientific claim", ["one.example", "two.example"]
            )

        self.assertTrue(checked.is_correct)
        self.assertEqual([item.evidence_id for item in checked.evidence], ["W2"])
        self.assertEqual(checked.evidence[0].url, "https://two.example/fact")
        self.assertEqual(checked.evidence[0].source_type, "web")

    def test_invalid_or_absent_web_evidence_cannot_support_a_claim(self) -> None:
        results = self.web_search.normalise_web_results(
            [{"title": "Source", "href": "https://source.example/fact", "body": "Snippet"}]
        )
        with (
            patch.object(self.web_search, "_ddg_results", return_value=results),
            patch.object(
                self.web_search.llm_client,
                "chat_with_tools",
                return_value={"verdict": "correct", "evidence_ids": ["W99"]},
            ),
        ):
            invalid = self.web_search.judge_web_evidence("A claim", ["source.example"])

        self.assertFalse(invalid.is_correct)
        self.assertEqual(invalid.evidence, [])

        with (
            patch.object(self.web_search, "_ddg_results", return_value=[]),
            patch.object(self.web_search.llm_client, "chat_with_tools") as chat,
        ):
            absent = self.web_search.judge_web_evidence("A claim", ["source.example"])

        self.assertFalse(absent.is_correct)
        self.assertEqual(absent.evidence, [])
        chat.assert_not_called()


class VerificationWebUpgradeTests(unittest.TestCase):
    def _syllabus_hit(self) -> dict:
        return {
            "score": 0.75,
            "text": "A syllabus passage that led to the original verdict.",
            "source_file": "science Grade 10 Part 1.pdf",
            "page_start": 30,
            "page_end": 30,
            "grade": 10,
            "topic": "Science · Grade 10 · Part 1",
            "subtopic": "Part 1",
            "document_type": "Syllabus & learner material",
        }

    def test_url_backed_web_result_replaces_syllabus_evidence_after_upgrade(self) -> None:
        from backend.components.knowledge_maps import verification

        web_item = schemas.EvidenceItem(
            evidence_id="W1",
            source_type="web",
            relation="supports",
            title="Trusted science source",
            excerpt="The selected web evidence.",
            url="https://science.example/fact",
            domain="science.example",
        )
        web_result = SimpleNamespace(verdict="correct", evidence=[web_item])
        raw = {
            "verdict": "incorrect",
            "explanation": "Not supported by the syllabus passage.",
            "corrected_version": "A correction",
            "evidence_ids": [],
        }
        with (
            patch.object(verification, "_extract_claims", return_value=["A globally correct claim."]),
            patch.object(verification, "retrieve", return_value=[self._syllabus_hit()]),
            patch.object(verification.llm_client, "chat_with_tools", return_value=raw),
            patch.object(verification, "judge_web_evidence", return_value=web_result),
        ):
            result = verification.verify_text("student note", object(), "en")

        claim = result.claims[0]
        self.assertEqual(claim.verdict, "correct")
        self.assertEqual(claim.source, "web")
        self.assertEqual(claim.evidence_status, "cited")
        self.assertEqual([item.evidence_id for item in claim.evidence], ["W1"])
        self.assertIsNone(claim.corrected_version)

    def test_uncited_web_result_does_not_upgrade_or_replace_syllabus_evidence(self) -> None:
        from backend.components.knowledge_maps import verification

        raw = {
            "verdict": "incorrect",
            "explanation": "The syllabus refutes the claim.",
            "evidence_ids": ["S1"],
        }
        with (
            patch.object(verification, "_extract_claims", return_value=["An incorrect claim."]),
            patch.object(verification, "retrieve", return_value=[self._syllabus_hit()]),
            patch.object(verification.llm_client, "chat_with_tools", return_value=raw),
            patch.object(verification, "judge_web_evidence") as web,
        ):
            result = verification.verify_text("student note", object(), "en")

        claim = result.claims[0]
        self.assertEqual(claim.verdict, "incorrect")
        self.assertEqual(claim.source, "syllabus")
        self.assertEqual([item.evidence_id for item in claim.evidence], ["S1"])
        web.assert_not_called()


class DocumentRouteTests(unittest.TestCase):
    def test_document_route_serves_known_pdf_inline_and_hides_unknown_ids(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from backend.components.knowledge_maps import router as routes

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "Resource"
            root.mkdir()
            book = root / "science.pdf"
            book.write_bytes(b"%PDF-1.4\nexact-test-document")
            document_id = evidence.document_id_for_source("science.pdf")

            app = FastAPI()
            app.include_router(routes.router, prefix="/api")
            with (
                patch.object(type(routes.settings), "resolved_resource_dir", return_value=root),
                TestClient(app) as client,
            ):
                found = client.get(f"/api/m4/documents/{document_id}")
                missing = client.get("/api/m4/documents/" + ("0" * 64))

        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.content, b"%PDF-1.4\nexact-test-document")
        self.assertEqual(found.headers["content-type"], "application/pdf")
        self.assertTrue(found.headers["content-disposition"].startswith("inline;"))
        self.assertEqual(found.headers["x-content-type-options"], "nosniff")
        self.assertIn("private", found.headers["cache-control"])
        self.assertEqual(missing.status_code, 404)
        self.assertNotIn(str(root), missing.text)


if __name__ == "__main__":
    unittest.main()
