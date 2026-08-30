#!/usr/bin/env python3
"""Fit and evaluate Member 4 confidence from anonymized teacher labels."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.components.knowledge_maps.confidence import FEATURE_ORDER
from backend.components.knowledge_maps.hybrid_retrieval import effective_retriever_signature

FORBIDDEN_CONTENT_KEYS = {"claim", "text", "name", "image", "student", "student_id"}
DECIDABLE = {"correct", "incorrect", "incomplete"}
RETRIEVER_SIGNATURE = effective_retriever_signature()


def validate_record(record: dict) -> None:
    if FORBIDDEN_CONTENT_KEYS.intersection(record):
        raise ValueError("Calibration records must not contain student content or identity fields")
    if record.get("split") not in {"train", "validation", "test"}:
        raise ValueError("split must be train, validation, or test")
    if record.get("gold_verdict") not in DECIDABLE | {"insufficient_evidence", "verification_failed"}:
        raise ValueError("invalid gold_verdict")
    if record.get("predicted_verdict") not in DECIDABLE | {"insufficient_evidence", "verification_failed"}:
        raise ValueError("invalid predicted_verdict")
    if not isinstance(record.get("signals"), dict):
        raise ValueError("signals must be an object")


def evaluate_probabilities(probabilities: list[float], labels: list[int]) -> dict:
    if not probabilities or len(probabilities) != len(labels):
        raise ValueError("probabilities and labels must be non-empty and equal length")
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(labels, dtype=float)
    brier = float(np.mean((p - y) ** 2))
    ece = 0.0
    for lower in np.linspace(0.0, 0.9, 10):
        upper = lower + 0.1
        mask = (p >= lower) & ((p < upper) if upper < 1.0 else (p <= upper))
        if mask.any():
            ece += float(mask.mean()) * abs(float(p[mask].mean()) - float(y[mask].mean()))
    thresholds = {}
    for threshold in (0.50, 0.60, 0.70, 0.80, 0.90):
        selected = p >= threshold
        thresholds[f"{threshold:.2f}"] = {
            "coverage": round(float(selected.mean()), 4),
            "selective_accuracy": round(float(y[selected].mean()), 4) if selected.any() else None,
            "examples": int(selected.sum()),
        }
    return {
        "examples": len(labels),
        "brier_score": round(brier, 6),
        "expected_calibration_error": round(ece, 6),
        "thresholds": thresholds,
    }


def _matrix(records: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    rows, labels = [], []
    for record in records:
        if record["predicted_verdict"] not in DECIDABLE:
            continue
        signals = record["signals"]
        rows.append([float(signals.get(name, 0.0)) for name in FEATURE_ORDER])
        labels.append(int(record["predicted_verdict"] == record["gold_verdict"]))
    if not rows:
        raise ValueError("split contains no decidable predictions")
    return np.asarray(rows, dtype=float), np.asarray(labels, dtype=float)


def _fit_logistic(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    weights = np.zeros(x.shape[1], dtype=float)
    intercept = 0.0
    for _ in range(4000):
        z = np.clip(x @ weights + intercept, -30, 30)
        predicted = 1.0 / (1.0 + np.exp(-z))
        error = predicted - y
        weights -= 0.05 * ((x.T @ error) / len(y) + 0.001 * weights)
        intercept -= 0.05 * float(error.mean())
    return weights, intercept


def _probabilities(x: np.ndarray, weights: np.ndarray, intercept: float) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x @ weights + intercept, -30, 30)))


def _group_accuracy(records: list[dict], key: str) -> dict:
    groups: dict[str, list[int]] = defaultdict(list)
    for row in records:
        groups[str(row.get(key, "unknown"))].append(
            int(row["gold_verdict"] == row["predicted_verdict"])
        )
    return {
        group: {"examples": len(values), "accuracy": round(sum(values) / len(values), 4)}
        for group, values in sorted(groups.items())
    }


def calibrate(records: list[dict]) -> tuple[dict, dict]:
    for record in records:
        validate_record(record)
    if not any(r["gold_verdict"] == "insufficient_evidence" for r in records):
        raise ValueError("dataset must include teacher-labelled insufficient_evidence cases")
    splits = {name: [r for r in records if r["split"] == name] for name in ("train", "validation", "test")}
    if any(not rows for rows in splits.values()):
        raise ValueError("train, validation, and test splits are all required")
    train_x, train_y = _matrix(splits["train"])
    weights, intercept = _fit_logistic(train_x, train_y)
    val_x, val_y = _matrix(splits["validation"])
    val_p = _probabilities(val_x, weights, intercept)

    high_threshold, high_precision, high_count = 0.95, 0.0, 0
    for threshold in (0.75, 0.80, 0.85, 0.90, 0.95):
        selected = val_p >= threshold
        precision = float(val_y[selected].mean()) if selected.any() else 0.0
        if int(selected.sum()) >= 20 and precision >= 0.90:
            high_threshold, high_precision, high_count = threshold, precision, int(selected.sum())
            break

    test_x, test_y = _matrix(splits["test"])
    test_p = _probabilities(test_x, weights, intercept)
    report = {
        "validation": evaluate_probabilities(val_p.tolist(), val_y.astype(int).tolist()),
        "test": evaluate_probabilities(test_p.tolist(), test_y.astype(int).tolist()),
        "by_verdict": _group_accuracy(splits["test"], "gold_verdict"),
        "by_language": _group_accuracy(splits["test"], "language"),
        "by_grade": _group_accuracy(splits["test"], "grade"),
        "by_source": _group_accuracy(splits["test"], "source"),
    }
    artifact = {
        "schema_version": 2,
        "model_id": "m4-teacher-platt-v2",
        "retriever_signature": RETRIEVER_SIGNATURE,
        "feature_order": list(FEATURE_ORDER),
        "coefficients": weights.tolist(),
        "intercept": float(intercept),
        "medium_threshold": 0.60,
        "high_threshold": high_threshold,
        "validation": {
            "examples": len(val_y),
            "high_confidence_examples": high_count,
            "precision_at_high": round(high_precision, 4),
        },
    }
    report["artifact_activates"] = (
        len(val_y) >= 100 and high_count >= 20 and high_precision >= 0.90
    )
    return artifact, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Anonymized teacher-labelled JSONL")
    parser.add_argument("--output", required=True, type=Path, help="Calibration artifact JSON")
    parser.add_argument("--report", type=Path, help="Optional evaluation report JSON")
    args = parser.parse_args()
    records = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    artifact, report = calibrate(records)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
