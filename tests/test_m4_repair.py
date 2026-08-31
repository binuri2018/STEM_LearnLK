from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.components.knowledge_maps.schemas import Claim, EvidenceItem, ScoreSummary, VerifyResponse


def cited_claim(text: str, verdict: str, *, claim_id: str, block_id: str) -> Claim:
    relation = "supports" if verdict == "correct" else "refutes" if verdict == "incorrect" else "context"
    return Claim(
        claim=text,
        claim_id=claim_id,
        source_block_id=block_id,
        source_start=2,
        source_end=2 + len(text),
        verdict=verdict,
        explanation="Evidence-backed decision.",
        evidence_status="cited",
        evidence=[EvidenceItem(
            evidence_id="S1",
            source_type="syllabus",
            relation=relation,
            title="Grade 10 Science",
            excerpt="Photosynthesis occurs in chloroplasts.",
            url="/api/m4/documents/abc#page=10",
            retrieval_score=0.7,
        )],
    )


def response(claims: list[Claim]) -> VerifyResponse:
    counts = {name: sum(c.verdict == name for c in claims) for name in (
        "correct", "incorrect", "incomplete", "insufficient_evidence", "verification_failed"
    )}
    decidable = counts["correct"] + counts["incorrect"] + counts["incomplete"]
    return VerifyResponse(
        overall_score=(counts["correct"] / decidable if decidable else None),
        score_summary=ScoreSummary(
            total_claims=len(claims), decidable_claims=decidable,
            coverage=(decidable / len(claims) if claims else 0), **counts,
        ),
        claims=claims,
    )


class NoteStructureTests(unittest.TestCase):
    def test_parser_round_trips_headings_blank_lines_lists_and_paragraphs(self) -> None:
        from backend.components.knowledge_maps.repair_note import parse_note_blocks

        text = "# Cells\n\n- Cellulose forms cell walls.\nParagraph line one.\nParagraph line two.\n"
        blocks = parse_note_blocks(text)

        self.assertEqual("".join(block.original_text for block in blocks), text)
        self.assertEqual(
            [block.block_type for block in blocks],
            ["heading", "blank", "list_item", "paragraph"],
        )
        self.assertEqual(blocks[2].marker, "- ")

    def test_source_fragment_must_be_unique_inside_its_block(self) -> None:
        from backend.components.knowledge_maps.repair_note import locate_source_fragment, parse_note_blocks

        unique = parse_note_blocks("- Plants respire.\n")[0]
        duplicate = parse_note_blocks("ATP and ATP are molecules.\n")[0]

        self.assertEqual(locate_source_fragment(unique, "Plants respire."), (2, 17))
        self.assertIsNone(locate_source_fragment(duplicate, "ATP"))

    def test_overlapping_fragments_are_rejected(self) -> None:
        from backend.components.knowledge_maps.repair_note import reject_overlapping_spans

        spans = [(0, 10), (5, 15), (20, 25)]

        self.assertEqual(reject_overlapping_spans(spans), [False, False, True])

    def test_structured_extraction_assigns_unique_server_claim_ids(self) -> None:
        from backend.components.knowledge_maps import repair_note

        blocks = repair_note.parse_note_blocks("First claim.\nSecond claim.\n")
        raw = {"claims": [
            {"claim_id": "duplicate", "block_id": "B1", "source_fragment": "First claim.", "claim": "First claim."},
            {"claim_id": "duplicate", "block_id": "B1", "source_fragment": "Second claim.", "claim": "Second claim."},
        ]}
        with patch.object(repair_note.llm_client, "chat_with_tools", return_value=raw):
            extracted = repair_note._extract_structured_claims(blocks, "en")

        self.assertEqual([item["claim_id"] for item in extracted], ["C1", "C2"])

    def test_locate_source_fragment_tolerates_whitespace_newline_case_and_dash(self) -> None:
        from backend.components.knowledge_maps.repair_note import locate_source_fragment, parse_note_blocks

        block = parse_note_blocks(
            "Cellular respiration releases\ncarbon-dioxide and water vapour.\n"
        )[0]
        span = locate_source_fragment(
            block, "cellular respiration releases carbon–dioxide and water vapour"
        )

        self.assertIsNotNone(span)
        self.assertEqual(
            block.original_text[span[0]:span[1]],
            "Cellular respiration releases\ncarbon-dioxide and water vapour",
        )
        # Exact / uniqueness contract is unchanged.
        unique = parse_note_blocks("- Plants respire.\n")[0]
        duplicate = parse_note_blocks("ATP and ATP are molecules.\n")[0]
        twice = parse_note_blocks("Water is vital. Water is vital.\n")[0]
        self.assertEqual(locate_source_fragment(unique, "Plants respire."), (2, 17))
        self.assertIsNone(locate_source_fragment(duplicate, "ATP"))
        self.assertIsNone(locate_source_fragment(twice, "water is vital"))

    def test_map_extracted_claims_corrects_renumbered_block_id(self) -> None:
        from backend.components.knowledge_maps import repair_note

        text = "# Sugars\n\nFructose is the sweetest sugar. Glucose is found in honey.\n"
        blocks = repair_note.parse_note_blocks(text)  # B1 heading, B2 blank, B3 paragraph
        rows = [{
            "claim_id": "C1", "block_id": "B2",  # model pointed at the hidden blank block
            "source_fragment": "Fructose is the sweetest sugar.",
            "claim": "Fructose is the sweetest sugar.",
        }]

        mapped = repair_note._map_extracted_claims(rows, blocks)

        self.assertEqual(mapped[0]["block_id"], "B3")
        self.assertEqual(mapped[0]["block_start"], 0)
        self.assertEqual(mapped[0]["source_start"], len("# Sugars\n\n"))

    def test_overlapping_mapped_spans_keep_earliest(self) -> None:
        from backend.components.knowledge_maps import repair_note

        blocks = repair_note.parse_note_blocks(
            "Glucose is a simple sugar found in sweet honey.\n"
        )
        rows = [
            {"claim_id": "C1", "block_id": "B1",
             "source_fragment": "Glucose is a simple sugar",
             "claim": "Glucose is a simple sugar"},
            {"claim_id": "C2", "block_id": "B1",
             "source_fragment": "simple sugar found in sweet honey",
             "claim": "simple sugar found in sweet honey"},
        ]

        mapped = repair_note._map_extracted_claims(rows, blocks)

        self.assertIsNotNone(mapped[0]["block_start"])
        self.assertIsNone(mapped[1]["block_start"])
        # The pure helper is untouched and still importable.
        self.assertEqual(
            repair_note.reject_overlapping_spans([(0, 10), (5, 15), (20, 25)]),
            [False, False, True],
        )


class RepairPipelineTests(unittest.TestCase):
    def test_cited_repair_is_independently_verified_and_inserted(self) -> None:
        from backend.components.knowledge_maps import repair_note

        text = "- Photosynthesis happens in mitochondria.\n- Chlorophyll absorbs light.\n"
        wrong = cited_claim(
            "Photosynthesis happens in mitochondria.", "incorrect", claim_id="C1", block_id="B1"
        )
        kept = cited_claim(
            "Chlorophyll absorbs light.", "correct", claim_id="C2", block_id="B2"
        )
        second = cited_claim(
            "Photosynthesis happens in chloroplasts.", "correct", claim_id="C1-R1", block_id="B1"
        )
        extracted = [
            {"claim_id": "C1", "block_id": "B1", "source_fragment": wrong.claim, "claim": wrong.claim},
            {"claim_id": "C2", "block_id": "B2", "source_fragment": kept.claim, "claim": kept.claim},
        ]
        with (
            patch.object(repair_note, "_extract_structured_claims", return_value=extracted),
            patch.object(repair_note, "verify_claims", side_effect=[response([wrong, kept]), response([second])]),
            patch.object(repair_note, "_propose_repair", return_value={
                "proposed_claim": second.claim,
                "change_reason": "The evidence identifies chloroplasts.",
                "evidence_ids": ["S1"],
            }),
            patch.object(repair_note, "_extract_tags", return_value=["photosynthesis"]),
        ):
            result = repair_note.run(text, "en", object(), preserve_structure=True)

        self.assertIn("Photosynthesis happens in chloroplasts.", result.repaired_note)
        self.assertIn("Chlorophyll absorbs light.", result.repaired_note)
        self.assertEqual(result.repairs[0].repair_status, "repaired")
        self.assertEqual(result.repairs[0].second_verdict, "correct")
        self.assertTrue(result.repairs[0].included_by_default)
        self.assertEqual(result.repairs[0].evidence[0].evidence_id, "S1")

    def test_unselected_repair_evidence_is_rejected_without_second_verification(self) -> None:
        from backend.components.knowledge_maps import repair_note

        text = "- Photosynthesis happens in mitochondria.\n"
        wrong = cited_claim(
            "Photosynthesis happens in mitochondria.", "incorrect", claim_id="C1", block_id="B1"
        )
        extracted = [{
            "claim_id": "C1", "block_id": "B1",
            "source_fragment": wrong.claim, "claim": wrong.claim,
        }]
        with (
            patch.object(repair_note, "_extract_structured_claims", return_value=extracted),
            patch.object(repair_note, "verify_claims", return_value=response([wrong])) as verify,
            patch.object(repair_note, "_propose_repair", return_value={
                "proposed_claim": "Photosynthesis happens in chloroplasts.",
                "change_reason": "Correction",
                "evidence_ids": None,
            }),
        ):
            result = repair_note.run(text, "en", object(), preserve_structure=True)

        self.assertEqual(verify.call_count, 1)
        self.assertEqual(result.repairs[0].repair_status, "unresolved")
        self.assertEqual(result.repairs[0].unresolved_reason, "invalid_proposal")
        # The unfixable sentence is kept as written; the rejected proposal is not inserted.
        self.assertIn("Photosynthesis happens in mitochondria.", result.repaired_note)
        self.assertNotIn("chloroplasts", result.repaired_note)

    def test_failed_second_verification_never_enters_clean_note(self) -> None:
        from backend.components.knowledge_maps import repair_note

        text = "- Photosynthesis happens in mitochondria.\n"
        wrong = cited_claim(
            "Photosynthesis happens in mitochondria.", "incorrect", claim_id="C1", block_id="B1"
        )
        failed = Claim(
            claim="Photosynthesis happens in chloroplasts.",
            verdict="verification_failed", explanation="Retry", source="none",
        )
        extracted = [{
            "claim_id": "C1", "block_id": "B1",
            "source_fragment": wrong.claim, "claim": wrong.claim,
        }]
        with (
            patch.object(repair_note, "_extract_structured_claims", return_value=extracted),
            patch.object(repair_note, "verify_claims", side_effect=[response([wrong]), response([failed])]),
            patch.object(repair_note, "_propose_repair", return_value={
                "proposed_claim": failed.claim,
                "change_reason": "Correction",
                "evidence_ids": ["S1"],
            }),
        ):
            result = repair_note.run(text, "en", object(), preserve_structure=True)

        self.assertEqual(result.repairs[0].repair_status, "unresolved")
        self.assertEqual(result.repairs[0].unresolved_reason, "second_verdict_not_correct")
        self.assertEqual(result.repairs[0].second_verdict, "verification_failed")
        self.assertNotIn("chloroplasts", result.repaired_note)

    def test_repaired_sibling_survives_unlocatable_unresolved_in_same_block(self) -> None:
        from backend.components.knowledge_maps import repair_note

        text = "Fructose is the sweetest sugar. Glucose is found in ripe fruits and bee honey.\n"
        wrong = cited_claim(
            "Fructose is the sweetest sugar.", "incorrect", claim_id="C1", block_id="B1"
        )
        other = Claim(
            claim="Glucose occurs only in laboratory solutions.",
            claim_id="C2", source_block_id="B1", verdict="insufficient_evidence",
            explanation="No syllabus evidence.", evidence_status="not_found",
        )
        second = cited_claim(
            "Sucrose forms from the union of a glucose and a fructose molecule.",
            "correct", claim_id="C1-R1", block_id="B1",
        )
        extracted = [
            {"claim_id": "C1", "block_id": "B1",
             "source_fragment": "Fructose is the sweetest sugar.", "claim": wrong.claim},
            {"claim_id": "C2", "block_id": "B1",
             "source_fragment": "glucose is grown in a lab dish",
             "claim": "Glucose occurs only in laboratory solutions."},
        ]
        with (
            patch.object(repair_note, "_extract_structured_claims", return_value=extracted),
            patch.object(repair_note, "verify_claims",
                         side_effect=[response([wrong, other]), response([second])]),
            patch.object(repair_note, "_propose_repair", return_value={
                "proposed_claim": second.claim,
                "change_reason": "The evidence describes sucrose.",
                "evidence_ids": ["S1"],
            }),
            patch.object(repair_note, "_extract_tags", return_value=["sugars"]),
        ):
            result = repair_note.run(text, "en", object(), preserve_structure=True)

        self.assertIn("Sucrose forms from the union", result.repaired_note)
        self.assertIn("Glucose is found in ripe fruits and bee honey.", result.repaired_note)
        self.assertNotIn("Fructose is the sweetest sugar.", result.repaired_note)
        self.assertTrue(result.repaired_note.strip())
        self.assertEqual(result.blocks[0].status, "repaired")
        self.assertIsNotNone(result.blocks[0].final_text)
        statuses = {record.claim_id: record.repair_status for record in result.repairs}
        self.assertEqual(statuses["C1"], "repaired")
        self.assertEqual(statuses["C2"], "unresolved")
        reasons = {record.claim_id: record.unresolved_reason for record in result.repairs}
        self.assertEqual(reasons["C2"], "invalid_span")

    def test_all_claims_unresolved_keep_full_original_text(self) -> None:
        from backend.components.knowledge_maps import repair_note

        text = "Mitochondria make food in green plants. Leaves exhale carbon at night.\n"
        c1 = Claim(
            claim="Cells manufacture sugar inside the leaf.", claim_id="C1",
            source_block_id="B1", verdict="insufficient_evidence",
            explanation="No evidence.", evidence_status="not_found",
        )
        c2 = Claim(
            claim="Trees breathe out carbon once it is dark.", claim_id="C2",
            source_block_id="B1", verdict="insufficient_evidence",
            explanation="No evidence.", evidence_status="not_found",
        )
        extracted = [
            {"claim_id": "C1", "block_id": "B1",
             "source_fragment": "cells make sugar in the leaf", "claim": c1.claim},
            {"claim_id": "C2", "block_id": "B1",
             "source_fragment": "trees breathe carbon after dark", "claim": c2.claim},
        ]
        with (
            patch.object(repair_note, "_extract_structured_claims", return_value=extracted),
            patch.object(repair_note, "verify_claims", return_value=response([c1, c2])) as verify,
            patch.object(repair_note, "_extract_tags", return_value=["cell biology"]),
        ):
            result = repair_note.run(text, "en", object(), preserve_structure=True)

        self.assertEqual(verify.call_count, 1)
        self.assertEqual(result.repaired_note, text)
        self.assertNotEqual(result.blocks[0].status, "excluded")
        self.assertIsNotNone(result.blocks[0].final_text)
        self.assertTrue(all(r.repair_status == "unresolved" for r in result.repairs))
        self.assertTrue(all(r.unresolved_reason == "invalid_span" for r in result.repairs))
        self.assertEqual(result.tags, ["cell biology"])


class RepairRouteTests(unittest.TestCase):
    def test_repair_endpoint_forwards_structure_flag_and_keeps_correct_note_route(self) -> None:
        from backend.components.knowledge_maps import router as routes
        from backend.components.knowledge_maps.schemas import RepairNoteRequest

        expected = object()
        body = RepairNoteRequest(
            text="A note.", response_language="en", preserve_structure=False
        )
        with (
            patch.object(routes, "_get_store", return_value="store"),
            patch.object(routes, "run_repair_note", return_value=expected) as run,
        ):
            actual = routes.repair_note_endpoint(body)

        self.assertIs(actual, expected)
        run.assert_called_once_with("A note.", "en", "store", preserve_structure=False)

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(routes.router, prefix="/api")
        with TestClient(app) as client:
            # A 503 (store not wired in this bare test app) still proves the
            # route exists and is reachable, unlike the 404 a missing route gives.
            self.assertNotEqual(client.post("/api/m4/repair-note", json={}).status_code, 404)
            self.assertNotEqual(client.post("/api/m4/correct-note", json={}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
