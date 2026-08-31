from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from backend.components.knowledge_maps.schemas import Claim, EvidenceItem


def syllabus_item(score: float = 0.62, evidence_id: str = "S1") -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        source_type="syllabus",
        relation="supports",
        title="Grade 10 Science",
        excerpt="Cellulose forms the plant cell wall.",
        url="/api/m4/documents/abc#page=10",
        retrieval_score=score,
    )


class ImprovementTwoSchemaTests(unittest.TestCase):
    def test_claim_accepts_all_five_states_and_rejects_unknown_state(self) -> None:
        for verdict in (
            "correct",
            "incorrect",
            "incomplete",
            "insufficient_evidence",
            "verification_failed",
        ):
            with self.subTest(verdict=verdict):
                claim = Claim(claim="A", verdict=verdict, explanation="Reason")
                self.assertEqual(claim.verdict, verdict)

        with self.assertRaises(ValidationError):
            Claim(claim="A", verdict="unknown", explanation="Reason")

    def test_score_summary_excludes_undecidable_claims(self) -> None:
        from backend.components.knowledge_maps.verification import response_for_claims

        verdicts = (
            ["correct"] * 6
            + ["incorrect", "incomplete", "insufficient_evidence", "verification_failed"]
        )
        response = response_for_claims(
            [Claim(claim=str(i), verdict=v, explanation="Reason") for i, v in enumerate(verdicts)]
        )

        self.assertEqual(response.overall_score, 0.75)
        self.assertEqual(response.score_summary.decidable_claims, 8)
        self.assertEqual(response.score_summary.coverage, 0.8)
        self.assertEqual(response.score_summary.insufficient_evidence, 1)
        self.assertEqual(response.score_summary.verification_failed, 1)

    def test_fully_undecidable_response_is_not_scored(self) -> None:
        from backend.components.knowledge_maps.verification import response_for_claims

        response = response_for_claims(
            [Claim(claim="A", verdict="insufficient_evidence", explanation="No evidence")]
        )

        self.assertIsNone(response.overall_score)
        self.assertEqual(response.score_summary.coverage, 0.0)


class ConfidenceTests(unittest.TestCase):
    def test_provisional_syllabus_bands_use_selected_scores_and_rank_gap(self) -> None:
        from backend.components.knowledge_maps.confidence import confidence_for_claim

        high = confidence_for_claim(
            verdict="correct",
            source="syllabus",
            evidence=[syllabus_item(0.62)],
            syllabus_hits=[{"score": 0.62}, {"score": 0.51}],
            evidence_status="cited",
        )
        medium = confidence_for_claim(
            verdict="correct",
            source="syllabus",
            evidence=[syllabus_item(0.50)],
            syllabus_hits=[{"score": 0.50}, {"score": 0.48}],
            evidence_status="cited",
        )
        low = confidence_for_claim(
            verdict="correct",
            source="syllabus",
            evidence=[syllabus_item(0.40)],
            syllabus_hits=[{"score": 0.40}, {"score": 0.39}],
            evidence_status="cited",
        )

        self.assertEqual((high.level, medium.level, low.level), ("high", "medium", "low"))
        self.assertEqual(high.status, "provisional")
        self.assertIsNone(high.probability)

    def test_web_is_never_provisionally_high_and_undecidable_is_unavailable(self) -> None:
        from backend.components.knowledge_maps.confidence import confidence_for_claim

        web = [
            EvidenceItem(
                evidence_id=f"W{i}", source_type="web", relation="supports",
                title="Source", excerpt="Evidence", url=f"https://source{i}.example/fact",
                domain=f"source{i}.example",
            )
            for i in (1, 2)
        ]
        medium = confidence_for_claim("correct", "web", web, [], "cited")
        unavailable = confidence_for_claim(
            "insufficient_evidence", "none", [], [], "not_found"
        )

        self.assertEqual(medium.level, "medium")
        self.assertEqual(unavailable.status, "unavailable")
        self.assertEqual(unavailable.level, "unavailable")

    def test_only_validated_artifact_enables_calibrated_probability(self) -> None:
        from backend.components.knowledge_maps.confidence import FEATURE_ORDER, confidence_for_claim

        artifact = {
            "schema_version": 1,
            "model_id": "teacher-calibration-v1",
            "feature_order": list(FEATURE_ORDER),
            "coefficients": [0.0] * len(FEATURE_ORDER),
            "intercept": 0.0,
            "medium_threshold": 0.6,
            "high_threshold": 0.8,
            "validation": {
                "examples": 120,
                "high_confidence_examples": 25,
                "precision_at_high": 0.92,
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            valid = Path(temp) / "valid.json"
            invalid = Path(temp) / "invalid.json"
            valid.write_text(json.dumps(artifact), encoding="utf-8")
            artifact["validation"]["precision_at_high"] = 0.89
            invalid.write_text(json.dumps(artifact), encoding="utf-8")

            calibrated = confidence_for_claim(
                "correct", "syllabus", [syllabus_item()], [{"score": 0.62}], "cited", valid
            )
            provisional = confidence_for_claim(
                "correct", "syllabus", [syllabus_item()], [{"score": 0.62}], "cited", invalid
            )

        self.assertEqual(calibrated.status, "calibrated")
        self.assertTrue(math.isclose(calibrated.probability or 0, 0.5))
        self.assertEqual(calibrated.method, "teacher-calibration-v1")
        self.assertEqual(provisional.status, "provisional")
        self.assertIsNone(provisional.probability)

    def test_nonnumeric_artifact_coefficients_fall_back_to_provisional(self) -> None:
        from backend.components.knowledge_maps.confidence import FEATURE_ORDER, confidence_for_claim

        artifact = {
            "schema_version": 1,
            "model_id": "broken",
            "feature_order": list(FEATURE_ORDER),
            "coefficients": ["not-a-number"] + [0.0] * (len(FEATURE_ORDER) - 1),
            "intercept": 0.0,
            "medium_threshold": 0.6,
            "high_threshold": 0.8,
            "validation": {"examples": 120, "high_confidence_examples": 25, "precision_at_high": 0.92},
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "artifact.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            result = confidence_for_claim(
                "correct", "syllabus", [syllabus_item()], [{"score": 0.62}], "cited", path
            )

        self.assertEqual(result.status, "provisional")

    def test_artifact_without_model_identity_falls_back_to_provisional(self) -> None:
        from backend.components.knowledge_maps.confidence import FEATURE_ORDER, confidence_for_claim

        artifact = {
            "schema_version": 1, "feature_order": list(FEATURE_ORDER),
            "coefficients": [0.0] * len(FEATURE_ORDER), "intercept": 0.0,
            "medium_threshold": 0.6, "high_threshold": 0.8,
            "validation": {"examples": 120, "high_confidence_examples": 25, "precision_at_high": 0.92},
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "artifact.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            result = confidence_for_claim(
                "correct", "syllabus", [syllabus_item()], [{"score": 0.62}], "cited", path
            )

        self.assertEqual(result.status, "provisional")


class EvidenceGatedVerificationTests(unittest.TestCase):
    def _hit(self) -> dict:
        return {
            "score": 0.65,
            "text": "Cellulose forms the plant cell wall.",
            "source_file": "science Grade 10 Part 1.pdf",
            "page_start": 10,
            "page_end": 10,
            "grade": 10,
        }

    def test_cited_syllabus_decision_does_not_call_web(self) -> None:
        from backend.components.knowledge_maps import verification

        with (
            patch.object(verification, "_extract_claims", return_value=["Plant walls contain cellulose."]),
            patch.object(verification, "retrieve", return_value=[self._hit()]),
            patch.object(
                verification.llm_client,
                "chat_with_tools",
                return_value={"verdict": "correct", "explanation": "Supported", "evidence_ids": ["S1"]},
            ),
            patch.object(verification, "judge_web_evidence") as web,
        ):
            result = verification.verify_text("note", object(), "en")

        self.assertEqual(result.claims[0].verdict, "correct")
        web.assert_not_called()

    def test_no_decisive_syllabus_or_web_evidence_is_insufficient(self) -> None:
        from backend.components.knowledge_maps import verification, web_search

        web_result = web_search.WebCheckResult(verdict="insufficient_evidence", evidence=[])
        with (
            patch.object(verification, "_extract_claims", return_value=["Algae grow on Mars."]),
            patch.object(verification, "retrieve", return_value=[]),
            patch.object(verification, "judge_web_evidence", return_value=web_result),
        ):
            result = verification.verify_text("note", object(), "en")

        self.assertEqual(result.claims[0].verdict, "insufficient_evidence")
        self.assertIsNone(result.overall_score)

    def test_unknown_model_verdict_is_verification_failed(self) -> None:
        from backend.components.knowledge_maps import verification

        with (
            patch.object(verification, "_extract_claims", return_value=["A claim."]),
            patch.object(verification, "retrieve", return_value=[self._hit()]),
            patch.object(
                verification.llm_client,
                "chat_with_tools",
                return_value={"verdict": "maybe", "explanation": "Unsure", "evidence_ids": ["S1"]},
            ),
        ):
            result = verification.verify_text("note", object(), "en")

        self.assertEqual(result.claims[0].verdict, "verification_failed")
        self.assertEqual(result.claims[0].source, "none")


class TrustedWebTests(unittest.TestCase):
    def test_allowlist_accepts_subdomains_and_can_refute(self) -> None:
        from backend.components.knowledge_maps import web_search

        results = web_search.normalise_web_results(
            [{"title": "Official", "href": "https://science.example.org/fact", "body": "The claim is false."}]
        )
        with (
            patch.object(web_search, "_ddg_results", return_value=results),
            patch.object(
                web_search.llm_client,
                "chat_with_tools",
                return_value={"verdict": "incorrect", "evidence_ids": ["W1"]},
            ),
        ):
            checked = web_search.judge_web_evidence("Claim", ["example.org"])

        self.assertEqual(checked.verdict, "incorrect")
        self.assertEqual(checked.evidence[0].relation, "refutes")

    def test_empty_allowlist_and_unapproved_results_fail_closed(self) -> None:
        from backend.components.knowledge_maps import web_search

        results = web_search.normalise_web_results(
            [{"title": "Random", "href": "https://random.example/fact", "body": "A snippet."}]
        )
        with patch.object(web_search, "_ddg_results", return_value=results):
            empty = web_search.judge_web_evidence("Claim", [])
            unapproved = web_search.judge_web_evidence("Claim", ["approved.example"])

        self.assertEqual(empty.verdict, "insufficient_evidence")
        self.assertEqual(unapproved.verdict, "insufficient_evidence")

    def test_malformed_web_judge_result_is_a_processing_failure(self) -> None:
        from backend.components.knowledge_maps import web_search

        results = web_search.normalise_web_results(
            [{"title": "Official", "href": "https://approved.example/fact", "body": "Evidence"}]
        )
        with (
            patch.object(web_search, "_ddg_results", return_value=results),
            patch.object(
                web_search.llm_client, "chat_with_tools",
                return_value={"verdict": "maybe", "evidence_ids": ["W1"]},
            ),
        ):
            with self.assertRaises(web_search.WebSearchUnavailable):
                web_search.judge_web_evidence("Claim", ["approved.example"])


class CorrectedNoteStateTests(unittest.TestCase):
    def test_corrected_note_separates_dropped_and_unresolved_claims(self) -> None:
        from backend.components.knowledge_maps import correct_note
        from backend.components.knowledge_maps.schemas import ScoreSummary, VerifyResponse

        correct = Claim(claim="Correct", verdict="correct", explanation="Supported", evidence_status="cited", evidence=[syllabus_item()])
        wrong = Claim(claim="Wrong", verdict="incorrect", explanation="Refuted")
        unresolved = Claim(claim="Unknown", verdict="insufficient_evidence", explanation="No evidence", source="none")
        verification = VerifyResponse(
            overall_score=0.5,
            score_summary=ScoreSummary(total_claims=3, decidable_claims=2, correct=1, incorrect=1, incomplete=0, insufficient_evidence=1, verification_failed=0, coverage=2 / 3),
            claims=[correct, wrong, unresolved],
        )
        with (
            patch.object(correct_note, "verify_text", return_value=verification),
            patch.object(correct_note, "_rewrite_note", return_value="Correct"),
            patch.object(correct_note, "_extract_tags", return_value=[]),
        ):
            result = correct_note.run("note", "en", object())

        self.assertEqual([c.claim for c in result.dropped_claims], ["Wrong"])
        self.assertEqual([c.claim for c in result.unresolved_claims], ["Unknown"])


class CalibrationCommandTests(unittest.TestCase):
    def test_calibration_artifact_is_bound_to_hybrid_retriever(self) -> None:
        from scripts.calibrate_m4_confidence import RETRIEVER_SIGNATURE, calibrate

        def row(split: str, gold: str = "correct") -> dict:
            return {
                "split": split,
                "gold_verdict": gold,
                "predicted_verdict": "correct" if gold != "insufficient_evidence" else "insufficient_evidence",
                "signals": {},
                "language": "en",
                "grade": 10,
                "source": "syllabus",
            }

        records = [row("train") for _ in range(5)]
        records += [row("train", "insufficient_evidence")]
        records += [row("validation") for _ in range(100)]
        records += [row("test") for _ in range(5)]

        artifact, _report = calibrate(records)

        self.assertEqual(artifact["schema_version"], 2)
        self.assertEqual(artifact["retriever_signature"], RETRIEVER_SIGNATURE)

    def test_documented_calibration_script_invocation_loads_project_modules(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [sys.executable, "scripts/calibrate_m4_confidence.py", "--help"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--input", completed.stdout)

    def test_metrics_report_selective_accuracy_coverage_brier_and_ece(self) -> None:
        from scripts.calibrate_m4_confidence import evaluate_probabilities

        report = evaluate_probabilities([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0])

        self.assertAlmostEqual(report["brier_score"], 0.025)
        self.assertIn("expected_calibration_error", report)
        self.assertEqual(report["thresholds"]["0.80"]["coverage"], 0.5)
        self.assertEqual(report["thresholds"]["0.80"]["selective_accuracy"], 1.0)

    def test_calibration_records_reject_student_content(self) -> None:
        from scripts.calibrate_m4_confidence import validate_record

        valid = {
            "split": "train", "gold_verdict": "correct", "predicted_verdict": "correct",
            "language": "en", "grade": 10, "source": "syllabus", "signals": {},
        }
        validate_record(valid)
        with self.assertRaisesRegex(ValueError, "student content"):
            validate_record({**valid, "claim": "A student's private note"})


if __name__ == "__main__":
    unittest.main()
