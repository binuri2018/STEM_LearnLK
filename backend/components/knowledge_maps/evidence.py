"""Build inspectable evidence records and safely resolve curriculum PDFs."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from typing import Literal

from backend.components.knowledge_maps.schemas import EvidenceItem

EvidenceStatus = Literal["cited", "not_found", "unavailable"]


def _normalise_source_file(source_file: str) -> str:
    raw = str(source_file or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        raise ValueError("source_file must be a relative resource path")

    path = PurePosixPath(raw)
    if any(part == ".." for part in path.parts):
        raise ValueError("source_file cannot contain parent traversal")

    normalised = "/".join(part for part in path.parts if part not in {"", "."})
    if not normalised:
        raise ValueError("source_file must identify a resource")
    return normalised


def document_id_for_source(source_file: str) -> str:
    """Return a stable opaque ID for a safe relative resource path."""
    normalised = _normalise_source_file(source_file)
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def resolve_document(document_id: str, resource_dir: Path) -> Path | None:
    """Resolve an opaque ID to a real PDF contained by ``resource_dir``."""
    if not re.fullmatch(r"[0-9a-f]{64}", str(document_id or "")):
        return None

    root = Path(resource_dir).resolve()
    if not root.is_dir():
        return None

    for candidate in root.rglob("*.pdf"):
        try:
            relative = candidate.relative_to(root)
            candidate_id = document_id_for_source(relative.as_posix())
            if candidate_id != document_id:
                continue
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, RuntimeError, ValueError):
            continue
        if resolved.is_file() and resolved.suffix.lower() == ".pdf":
            return resolved
    return None


def relation_for_verdict(verdict: str) -> Literal["supports", "refutes", "context"]:
    if verdict == "correct":
        return "supports"
    if verdict == "incorrect":
        return "refutes"
    return "context"


def _syllabus_item(hit: dict, verdict: str) -> EvidenceItem:
    source_file = _normalise_source_file(str(hit.get("source_file") or ""))
    document_id = document_id_for_source(source_file)
    page_start = hit.get("page_start")
    page_end = hit.get("page_end")
    url = f"/api/m4/documents/{document_id}"
    if isinstance(page_start, int) and page_start > 0:
        url += f"#page={page_start}"

    raw_score = hit.get("score")
    retrieval_score = float(raw_score) if isinstance(raw_score, (int, float)) else None

    return EvidenceItem(
        evidence_id=str(hit.get("evidence_id") or ""),
        source_type="syllabus",
        relation=relation_for_verdict(verdict),
        title=PurePosixPath(source_file).stem,
        excerpt=str(hit.get("text") or ""),
        url=url,
        document_id=document_id,
        pdf_page_start=page_start if isinstance(page_start, int) else None,
        pdf_page_end=page_end if isinstance(page_end, int) else None,
        grade=hit.get("grade") if isinstance(hit.get("grade"), int) else None,
        topic=str(hit["topic"]) if hit.get("topic") is not None else None,
        subtopic=str(hit["subtopic"]) if hit.get("subtopic") is not None else None,
        document_type=(
            str(hit["document_type"]) if hit.get("document_type") is not None else None
        ),
        retrieval_score=retrieval_score,
        retrieval_method=(str(hit["retrieval_method"]) if hit.get("retrieval_method") else None),
        dense_score=(float(hit["dense_score"]) if isinstance(hit.get("dense_score"), (int, float)) else None),
        keyword_score=(float(hit["keyword_score"]) if isinstance(hit.get("keyword_score"), (int, float)) else None),
        fusion_score=(float(hit["fusion_score"]) if isinstance(hit.get("fusion_score"), (int, float)) else None),
        reranker_score=(float(hit["reranker_score"]) if isinstance(hit.get("reranker_score"), (int, float)) else None),
    )


def select_syllabus_evidence(
    hits: list[dict],
    selected_ids: object,
    verdict: str,
) -> tuple[list[EvidenceItem], EvidenceStatus]:
    """Return selected, valid syllabus citations without inventing a fallback."""
    if not hits:
        return [], "not_found"

    if not isinstance(selected_ids, list):
        return [], "unavailable"
    wanted = {str(value) for value in selected_ids if isinstance(value, str)}
    selected: list[EvidenceItem] = []
    for hit in hits:
        evidence_id = hit.get("evidence_id")
        if not isinstance(evidence_id, str) or evidence_id not in wanted:
            continue
        try:
            selected.append(_syllabus_item(hit, verdict))
        except (TypeError, ValueError):
            continue

    if not selected:
        return [], "unavailable"
    return selected, "cited"
