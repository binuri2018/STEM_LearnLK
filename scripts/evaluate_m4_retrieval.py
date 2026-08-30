#!/usr/bin/env python3
"""Evaluate Member 4 dense, hybrid, expansion, and reranked retrieval."""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.common.config import settings
from backend.components.knowledge_maps.hybrid_retrieval import HybridRetriever, chunk_id_for_metadata, effective_retriever_signature
from backend.common.vector_store import VectorStore

RETRIEVER_SIGNATURE = effective_retriever_signature()


def retrieval_metrics(cases: list[tuple[set[str], list[str]]]) -> dict:
    if not cases:
        raise ValueError("at least one retrieval case is required")
    recalls: dict[int, float] = {}
    for k in (1, 3, 5, 10):
        recalls[k] = sum(bool(gold.intersection(ranking[:k])) for gold, ranking in cases) / len(cases)
    reciprocal = []
    for gold, ranking in cases:
        rank = next((index for index, item in enumerate(ranking, start=1) if item in gold), None)
        reciprocal.append(1.0 / rank if rank else 0.0)
    return {
        **{f"recall_at_{k}": round(value, 4) for k, value in recalls.items()},
        "mrr": round(sum(reciprocal) / len(reciprocal), 4),
        "examples": len(cases),
    }


def evidence_sufficiency_accuracy(cases: list[tuple[bool, bool]]) -> float:
    if not cases:
        raise ValueError("at least one evidence-sufficiency case is required")
    return round(sum(expected == predicted for expected, predicted in cases) / len(cases), 4)


def select_reranker_threshold(rows: list[dict]) -> dict:
    validation = [row for row in rows if row.get("split") == "validation"]
    if not validation:
        raise ValueError("validation rows are required for threshold selection")
    positives = sum(bool(row.get("sufficient")) for row in validation)
    candidates = sorted({float(row["score"]) for row in validation})
    best: tuple[float, float, float, float, int] | None = None
    for threshold in candidates:
        selected = [row for row in validation if float(row["score"]) >= threshold]
        true_positive = sum(bool(row.get("sufficient")) for row in selected)
        precision = true_positive / len(selected) if selected else 0.0
        recall = true_positive / positives if positives else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        candidate = (f1, precision, recall, threshold, len(selected))
        if best is None or candidate > best:
            best = candidate
    assert best is not None
    f1, precision, recall, threshold, count = best
    return {
        "split": "validation",
        "threshold": threshold,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "selected_examples": count,
    }


def _validate_record(record: dict) -> None:
    required = {"id", "split", "claim", "language", "grade", "unit", "claim_type", "relevant"}
    missing = sorted(required.difference(record))
    if missing:
        raise ValueError(f"evaluation record is missing: {', '.join(missing)}")
    if record["split"] not in {"train", "validation", "test"}:
        raise ValueError("split must be train, validation, or test")
    if not isinstance(record["relevant"], list):
        raise ValueError("relevant must be a list of source/page objects")
    if not record["relevant"] and record.get("evidence_sufficient", True):
        raise ValueError("an evidence-sufficient record requires relevant evidence")


def _gold_ids(record: dict, store: VectorStore) -> set[str]:
    output: set[str] = set()
    for expected in record["relevant"]:
        for meta in store.metadatas:
            if (
                str(meta.get("source_file")) == str(expected.get("source_file"))
                and meta.get("page_start") == expected.get("page_start")
                and meta.get("page_end") == expected.get("page_end", expected.get("page_start"))
            ):
                output.add(chunk_id_for_metadata(meta))
    return output


def _group_report(rows: list[dict], key: str) -> dict:
    groups: dict[str, list[tuple[set[str], list[str]]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(key, "unknown"))].append((row["gold"], row["ranking"]))
    return {name: retrieval_metrics(cases) for name, cases in sorted(groups.items())}


def evaluate(records: list[dict], store: VectorStore, include_reranker: bool = True) -> tuple[dict, dict]:
    for record in records:
        _validate_record(record)
    retriever = HybridRetriever(store)
    variants = {
        "dense_top3": dict(dense_k=3, keyword_k=1, fused_k=3, final_k=3, use_reranker=False, keyword=False, expansion=False),
        "dense_top20": dict(dense_k=20, keyword_k=1, fused_k=20, final_k=20, use_reranker=False, keyword=False, expansion=False),
        "hybrid_rrf": dict(dense_k=20, keyword_k=20, fused_k=20, final_k=10, use_reranker=False, keyword=True, expansion=False),
        "hybrid_rrf_expanded": dict(dense_k=20, keyword_k=20, fused_k=20, final_k=10, use_reranker=False, keyword=True, expansion=True),
    }
    if include_reranker:
        variants["hybrid_reranked"] = dict(
            dense_k=20, keyword_k=20, fused_k=20, final_k=10,
            use_reranker=True, keyword=True, expansion=True,
        )

    report: dict[str, dict] = {}
    threshold_rows: list[dict] = []
    for name, options in variants.items():
        evaluated = []
        elapsed = []
        for record in records:
            gold = _gold_ids(record, store)
            started = time.perf_counter()
            if options["keyword"]:
                hits = retriever.retrieve(
                    str(record["claim"]),
                    use_expansion=bool(options["expansion"]),
                    **{k: v for k, v in options.items() if k not in {"expansion", "keyword"}},
                )
            else:
                dense_hits = retriever._dense(str(record["claim"]), int(options["dense_k"]))
                hits = dense_hits[: int(options["final_k"])]
            elapsed.append((time.perf_counter() - started) * 1000)
            ranking = [str(hit["chunk_id"]) for hit in hits]
            predicted_sufficient = bool(gold.intersection(ranking[:5]))
            evaluated.append({
                **record,
                "gold": gold,
                "ranking": ranking,
                "expected_sufficient": bool(record.get("evidence_sufficient", bool(gold))),
                "predicted_sufficient": predicted_sufficient,
            })
            if name == "hybrid_reranked" and hits:
                threshold_rows.extend({
                    "split": record["split"],
                    "score": float(hit.get("reranker_score") or 0.0),
                    "sufficient": str(hit["chunk_id"]) in gold,
                } for hit in hits)
        cases = [(row["gold"], row["ranking"]) for row in evaluated]
        report[name] = {
            **retrieval_metrics(cases),
            "evidence_sufficiency_accuracy": evidence_sufficiency_accuracy([
                (row["expected_sufficient"], row["predicted_sufficient"])
                for row in evaluated
            ]),
            "mean_latency_ms": round(sum(elapsed) / len(elapsed), 2),
            "by_split": _group_report(evaluated, "split"),
            "by_language": _group_report(evaluated, "language"),
            "by_grade": _group_report(evaluated, "grade"),
            "by_unit": _group_report(evaluated, "unit"),
            "by_claim_type": _group_report(evaluated, "claim_type"),
        }

    threshold = select_reranker_threshold(threshold_rows) if threshold_rows else None
    resolved_revision = getattr(retriever.reranker, "resolved_revision", None) or settings.m4_reranker_revision
    policy = {
        "schema_version": 1,
        "retriever_signature": effective_retriever_signature(reranker_revision=resolved_revision),
        "reranker_model": settings.m4_reranker_model,
        "reranker_revision": resolved_revision,
        "minimum_reranker_score": threshold["threshold"] if threshold else None,
        "validation": threshold,
    }
    return report, policy


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Teacher-labelled retrieval JSONL")
    parser.add_argument("--report", required=True, type=Path, help="Output metrics JSON")
    parser.add_argument("--policy", type=Path, help="Optional validated retrieval-policy JSON")
    parser.add_argument("--no-reranker", action="store_true", help="Skip the local cross-encoder run")
    args = parser.parse_args()

    records = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    store = VectorStore.load(settings.resolved_data_dir())
    report, policy = evaluate(records, store, include_reranker=not args.no_reranker)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.policy:
        args.policy.parent.mkdir(parents=True, exist_ok=True)
        args.policy.write_text(json.dumps(policy, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
