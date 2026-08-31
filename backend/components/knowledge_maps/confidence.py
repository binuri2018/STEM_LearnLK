"""Transparent evidence strength and optional offline-calibrated confidence."""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from backend.components.knowledge_maps.schemas import ConfidenceInfo, EvidenceItem

logger = logging.getLogger(__name__)

FEATURE_ORDER = (
    "top_score", "score_gap", "selected_count", "selected_max_score",
    "selected_mean_score", "evidence_cited", "source_syllabus", "source_web",
    "web_domain_count", "verdict_correct", "verdict_incorrect", "verdict_incomplete",
)


def _numeric_scores(hits: list[dict]) -> list[float]:
    return sorted(
        [float(h["score"]) for h in hits if isinstance(h.get("score"), (int, float))],
        reverse=True,
    )


def extract_confidence_signals(
    verdict: str,
    source: str,
    evidence: list[EvidenceItem],
    syllabus_hits: list[dict],
    evidence_status: str,
) -> dict[str, float]:
    ranked = _numeric_scores(syllabus_hits)
    selected_scores = [
        float(item.retrieval_score)
        for item in evidence
        if item.retrieval_score is not None
    ]
    domains = {item.domain.lower() for item in evidence if item.domain}
    return {
        "top_score": ranked[0] if ranked else 0.0,
        "score_gap": max(ranked[0] - ranked[1], 0.0) if len(ranked) > 1 else 0.0,
        "selected_count": float(len(evidence)),
        "selected_max_score": max(selected_scores, default=0.0),
        "selected_mean_score": sum(selected_scores) / len(selected_scores) if selected_scores else 0.0,
        "evidence_cited": float(evidence_status == "cited"),
        "source_syllabus": float(source == "syllabus"),
        "source_web": float(source == "web"),
        "web_domain_count": float(len(domains)),
        "verdict_correct": float(verdict == "correct"),
        "verdict_incorrect": float(verdict == "incorrect"),
        "verdict_incomplete": float(verdict == "incomplete"),
    }


def _load_artifact(path: Path | None, retriever_signature: str) -> dict | None:
    if path is None or not Path(path).is_file():
        return None
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        validation = raw["validation"]
        coefficients = [float(value) for value in raw.get("coefficients", [])]
        intercept = float(raw["intercept"])
        medium_threshold = float(raw.get("medium_threshold", 0.6))
        high_threshold = float(raw.get("high_threshold", 0))
        schema_version = raw.get("schema_version")
        signature_matches = (
            (schema_version == 1 and retriever_signature == "dense_top3_v1")
            or (
                schema_version == 2
                and raw.get("retriever_signature") == retriever_signature
            )
        )
        valid = (
            signature_matches
            and isinstance(raw.get("model_id"), str)
            and bool(raw.get("model_id", "").strip())
            and tuple(raw.get("feature_order", [])) == FEATURE_ORDER
            and len(coefficients) == len(FEATURE_ORDER)
            and math.isfinite(intercept)
            and all(math.isfinite(value) for value in coefficients)
            and 0.0 <= medium_threshold <= 1.0
            and 0.0 <= high_threshold <= 1.0
            and medium_threshold < high_threshold
            and int(validation.get("examples", 0)) >= 100
            and int(validation.get("high_confidence_examples", 0)) >= 20
            and float(validation.get("precision_at_high", 0)) >= 0.90
            and high_threshold >= 0.75
        )
        if not valid:
            raise ValueError("artifact does not meet activation gates")
        raw["coefficients"] = coefficients
        raw["intercept"] = intercept
        raw["medium_threshold"] = medium_threshold
        raw["high_threshold"] = high_threshold
        return raw
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("Ignoring invalid confidence artifact %s: %s", path, exc)
        return None


def confidence_for_claim(
    verdict: str,
    source: str,
    evidence: list[EvidenceItem],
    syllabus_hits: list[dict],
    evidence_status: str,
    artifact_path: Path | None = None,
    retriever_signature: str = "dense_top3_v1",
) -> ConfidenceInfo:
    if verdict not in {"correct", "incorrect", "incomplete"} or evidence_status != "cited":
        return ConfidenceInfo(
            reasons=["The claim could not be assigned an evidence-backed educational verdict."]
        )

    signals = extract_confidence_signals(verdict, source, evidence, syllabus_hits, evidence_status)
    artifact = _load_artifact(artifact_path, retriever_signature)
    if artifact:
        linear = float(artifact["intercept"]) + sum(
            float(weight) * signals[name]
            for name, weight in zip(FEATURE_ORDER, artifact["coefficients"])
        )
        probability = 1.0 / (1.0 + math.exp(-max(min(linear, 700), -700)))
        if probability >= float(artifact["high_threshold"]):
            level = "high"
        elif probability >= float(artifact.get("medium_threshold", 0.6)):
            level = "medium"
        else:
            level = "low"
        return ConfidenceInfo(
            status="calibrated", level=level, probability=round(probability, 4),
            method=str(artifact["model_id"]), reasons=["Calibrated against teacher-labelled verdict outcomes."],
        )

    if source == "web":
        domains = int(signals["web_domain_count"])
        level = "medium" if domains >= 2 else "low"
        reason = f"Selected evidence comes from {domains} approved web domain{'s' if domains != 1 else ''}."
    else:
        score = signals["selected_max_score"]
        high = score >= 0.60 and (
            signals["selected_count"] >= 2 or signals["score_gap"] >= 0.08
        )
        level = "high" if high else "medium" if score >= 0.45 else "low"
        reason = f"Highest selected syllabus similarity is {score:.2f}."
    return ConfidenceInfo(
        status="provisional", level=level, probability=None,
        method=("evidence_rules_hybrid_v1" if retriever_signature != "dense_top3_v1" else "evidence_rules_v1"),
        reasons=[reason],
    )
