from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class HybridRetrievalPrimitiveTests(unittest.TestCase):
    def test_normalization_preserves_sinhala_formulas_and_normalizes_latin(self) -> None:
        from backend.components.knowledge_maps.hybrid_retrieval import normalise_query, tokenise

        normalized = normalise_query("  CELL   ශ්වසනය  H₂O + CO₂  ")

        self.assertEqual(normalized, "cell ශ්වසනය h2o + co2")
        self.assertEqual(tokenise(normalized), ["cell", "ශ්වසනය", "h2o", "+", "co2"])

    def test_chunk_id_is_deterministic_across_path_separator_styles(self) -> None:
        from backend.components.knowledge_maps.hybrid_retrieval import chunk_id_for_metadata

        left = {
            "source_file": "grade10/science.pdf",
            "page_start": 7,
            "page_end": 7,
            "text": "Photosynthesis occurs in chloroplasts.",
        }
        right = {**left, "source_file": r"grade10\science.pdf"}

        self.assertEqual(chunk_id_for_metadata(left), chunk_id_for_metadata(right))

    def test_rrf_merges_duplicate_chunks_and_rewards_two_rankings(self) -> None:
        from backend.components.knowledge_maps.hybrid_retrieval import reciprocal_rank_fusion

        dense = [
            {"chunk_id": "a", "dense_score": 0.8},
            {"chunk_id": "b", "dense_score": 0.7},
        ]
        keyword = [
            {"chunk_id": "b", "keyword_score": 5.0},
            {"chunk_id": "c", "keyword_score": 4.0},
        ]

        fused = reciprocal_rank_fusion(dense, keyword, rrf_k=60)

        self.assertEqual([row["chunk_id"] for row in fused], ["b", "a", "c"])
        self.assertIn("dense_score", fused[0])
        self.assertIn("keyword_score", fused[0])

    def test_curated_expansion_is_exact_and_capped(self) -> None:
        from backend.components.knowledge_maps.hybrid_retrieval import QueryGlossary

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "glossary.json"
            path.write_text(
                json.dumps({
                    "food-making part": ["photosynthesis", "chloroplast", "chlorophyll"],
                    "cell": ["cellule"],
                }),
                encoding="utf-8",
            )
            glossary = QueryGlossary.load(path)

        self.assertEqual(
            glossary.expand("The food-making part", limit=2),
            ["photosynthesis", "chloroplast"],
        )
        self.assertEqual(glossary.expand("cellular", limit=5), [])


class HybridRetrieverTests(unittest.TestCase):
    def _store(self):
        from backend.common.vector_store import VectorStore

        store = VectorStore(dim=2)
        store.metadatas = [
            {
                "text": "general plant cell information",
                "source_file": "book.pdf",
                "page_start": 1,
                "page_end": 1,
            },
            {
                "text": "chloroplast is the site of photosynthesis",
                "source_file": "book.pdf",
                "page_start": 2,
                "page_end": 2,
            },
            {
                "text": "respiration releases energy from food",
                "source_file": "book.pdf",
                "page_start": 3,
                "page_end": 3,
            },
        ]
        return store

    def test_keyword_only_candidate_survives_and_reranker_diagnostics_are_exposed(self) -> None:
        from backend.components.knowledge_maps.hybrid_retrieval import HybridRetriever

        store = self._store()
        retriever = HybridRetriever(
            store,
            reranker=lambda pairs: [0.1, 0.9],
            query_embedder=lambda _query: [1.0, 0.0],
        )
        dense = [
            (0.75, store.metadatas[0]),
        ]

        with patch.object(store, "search", return_value=dense):
            hits = retriever.retrieve("chloroplast", final_k=2)

        self.assertEqual(hits[0]["page_start"], 2)
        self.assertEqual(hits[0]["retrieval_method"], "hybrid_reranked")
        self.assertIsNone(hits[0]["dense_score"])
        self.assertGreater(hits[0]["keyword_score"], 0)
        self.assertEqual(hits[0]["reranker_score"], 0.9)

    def test_reranker_failure_falls_back_to_rrf_without_claiming_reranking(self) -> None:
        from backend.components.knowledge_maps.hybrid_retrieval import HybridRetriever

        def broken(_pairs):
            raise RuntimeError("model unavailable")

        store = self._store()
        retriever = HybridRetriever(
            store,
            reranker=broken,
            query_embedder=lambda _query: [1.0, 0.0],
        )
        with patch.object(store, "search", return_value=[(0.8, store.metadatas[0])]):
            hits = retriever.retrieve("chloroplast", final_k=2)

        self.assertTrue(hits)
        self.assertTrue(all(hit["retrieval_method"] == "hybrid_rrf" for hit in hits))
        self.assertTrue(all(hit["reranker_score"] is None for hit in hits))

    def test_only_matching_validated_policy_applies_reranker_cutoff(self) -> None:
        from backend.components.knowledge_maps.hybrid_retrieval import HybridRetriever, effective_retriever_signature

        store = self._store()
        retriever = HybridRetriever(
            store,
            reranker=lambda _pairs: [0.6, 0.8],
            query_embedder=lambda _query: [1.0, 0.0],
            policy={
                "schema_version": 1,
                "retriever_signature": effective_retriever_signature(),
                "reranker_model": "BAAI/bge-reranker-v2-m3",
                "reranker_revision": "test-revision",
                "minimum_reranker_score": 0.75,
                "validation": {"split": "validation"},
            },
        )
        with patch.object(store, "search", return_value=[(0.8, store.metadatas[0])]):
            hits = retriever.retrieve("chloroplast", final_k=2)

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["reranker_score"], 0.8)

    def test_policy_requires_a_pinned_matching_reranker_revision(self) -> None:
        from backend.components.knowledge_maps import hybrid_retrieval

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "policy.json"
            with patch.object(hybrid_retrieval.settings, "m4_reranker_revision", "abc123"):
                path.write_text(json.dumps({
                    "schema_version": 1,
                    "retriever_signature": hybrid_retrieval.effective_retriever_signature(),
                    "reranker_model": hybrid_retrieval.settings.m4_reranker_model,
                    "reranker_revision": "abc123",
                    "minimum_reranker_score": 0.5,
                    "validation": {"split": "validation"},
                }), encoding="utf-8")
                self.assertIsNotNone(hybrid_retrieval.load_retrieval_policy(path))
            with patch.object(hybrid_retrieval.settings, "m4_reranker_revision", None):
                self.assertIsNone(hybrid_retrieval.load_retrieval_policy(path))

    def test_lazy_reranker_does_not_repeat_a_failed_model_load(self) -> None:
        from backend.components.knowledge_maps.hybrid_retrieval import LazyCrossEncoderReranker

        attempts = 0

        def broken_loader(_name, **_kwargs):
            nonlocal attempts
            attempts += 1
            raise RuntimeError("offline")

        reranker = LazyCrossEncoderReranker("model", model_loader=broken_loader)
        for _ in range(2):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                reranker([("query", "passage")])

        self.assertEqual(attempts, 1)


class HybridIntegrationContractTests(unittest.TestCase):
    def test_member4_verification_uses_hybrid_retrieval_without_dense_cutoff(self) -> None:
        from backend.components.knowledge_maps import verification

        low_dense_hit = {
            "score": 0.12,
            "dense_score": 0.12,
            "keyword_score": 7.0,
            "fusion_score": 0.03,
            "reranker_score": 0.91,
            "retrieval_method": "hybrid_reranked",
            "text": "The vena cava carries deoxygenated blood to the right atrium.",
            "source_file": "science.pdf",
            "page_start": 9,
            "page_end": 9,
        }
        fake = type(
            "Retriever", (),
            {"retrieve": lambda self, _query, **_kwargs: [low_dense_hit]},
        )()

        with (
            patch.object(verification, "get_hybrid_retriever", return_value=fake),
            patch.object(
                verification.llm_client,
                "chat_with_tools",
                return_value={"verdict": "correct", "explanation": "Supported", "evidence_ids": ["S1"]},
            ),
        ):
            raw, hits = verification._verdict_for_claim("Vena cava claim", object(), "en")

        self.assertEqual(raw["verdict"], "correct")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["evidence_id"], "S1")

    def test_syllabus_evidence_exposes_hybrid_score_components(self) -> None:
        from backend.components.knowledge_maps.evidence import select_syllabus_evidence

        hit = {
            "evidence_id": "S1",
            "text": "Direct evidence.",
            "source_file": "science.pdf",
            "page_start": 4,
            "page_end": 4,
            "score": 0.4,
            "dense_score": 0.4,
            "keyword_score": 3.2,
            "fusion_score": 0.03,
            "reranker_score": 0.88,
            "retrieval_method": "hybrid_reranked",
        }

        items, status = select_syllabus_evidence([hit], ["S1"], "correct")

        self.assertEqual(status, "cited")
        self.assertEqual(items[0].retrieval_method, "hybrid_reranked")
        self.assertEqual(items[0].dense_score, 0.4)
        self.assertEqual(items[0].reranker_score, 0.88)

    def test_confidence_artifact_requires_matching_hybrid_retriever_signature(self) -> None:
        from backend.components.knowledge_maps.confidence import FEATURE_ORDER, confidence_for_claim
        from backend.components.knowledge_maps.schemas import EvidenceItem

        artifact = {
            "schema_version": 2,
            "model_id": "teacher-calibration-v2",
            "retriever_signature": "dense_top3_v1",
            "feature_order": list(FEATURE_ORDER),
            "coefficients": [0.0] * len(FEATURE_ORDER),
            "intercept": 0.0,
            "medium_threshold": 0.6,
            "high_threshold": 0.8,
            "validation": {"examples": 120, "high_confidence_examples": 25, "precision_at_high": 0.92},
        }
        item = EvidenceItem(
            evidence_id="S1", source_type="syllabus", relation="supports",
            title="Book", excerpt="Evidence", url="/pdf", retrieval_score=0.7,
        )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "artifact.json"
            path.write_text(json.dumps(artifact), encoding="utf-8")
            result = confidence_for_claim(
                "correct", "syllabus", [item], [{"score": 0.7}], "cited", path,
                retriever_signature="hybrid_bm25_rrf_bge_v1",
            )

        self.assertEqual(result.status, "provisional")

    def test_health_exposes_retrieval_and_reranker_status(self) -> None:
        from backend.components.knowledge_maps import router as routes

        fake_retriever = type("Retriever", (), {"status": lambda self: {
            "retrieval_method": "hybrid_reranked",
            "reranker_model": "model",
            "reranker_revision": "revision",
            "reranker_loaded": True,
            "reranker_error": None,
        }})()
        with (
            patch.object(routes.llm_client, "is_configured", return_value=False),
            patch("backend.main._store", object()),
            patch.object(routes, "get_hybrid_retriever", return_value=fake_retriever),
        ):
            payload = routes.health().model_dump()

        self.assertEqual(payload["retrieval_method"], "hybrid_reranked")
        self.assertTrue(payload["reranker_loaded"])


class RetrievalEvaluationTests(unittest.TestCase):
    def test_metrics_report_recall_and_reciprocal_rank_from_literal_rankings(self) -> None:
        from scripts.evaluate_m4_retrieval import evidence_sufficiency_accuracy, retrieval_metrics

        metrics = retrieval_metrics([
            ({"gold-a"}, ["wrong", "gold-a"]),
            ({"gold-b"}, ["gold-b", "other"]),
        ])

        self.assertEqual(metrics["recall_at_1"], 0.5)
        self.assertEqual(metrics["recall_at_3"], 1.0)
        self.assertEqual(metrics["mrr"], 0.75)
        self.assertEqual(
            evidence_sufficiency_accuracy([(True, True), (False, True)]),
            0.5,
        )

    def test_threshold_selection_uses_validation_rows_only(self) -> None:
        from scripts.evaluate_m4_retrieval import select_reranker_threshold

        rows = [
            {"split": "train", "score": 0.99, "sufficient": False},
            {"split": "validation", "score": 0.9, "sufficient": True},
            {"split": "validation", "score": 0.8, "sufficient": True},
            {"split": "validation", "score": 0.7, "sufficient": False},
        ]

        selected = select_reranker_threshold(rows)

        self.assertEqual(selected["split"], "validation")
        self.assertEqual(selected["threshold"], 0.8)
        self.assertEqual(selected["precision"], 1.0)

    def test_documented_evaluation_command_loads(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [sys.executable, "scripts/evaluate_m4_retrieval.py", "--help"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--input", completed.stdout)


if __name__ == "__main__":
    unittest.main()
