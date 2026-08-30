"""Retrieve top-k syllabus chunks for a query."""
from __future__ import annotations

import numpy as np

from backend.common.config import settings
from backend.common.embeddings import embed_query
from backend.common.vector_store import VectorStore


def retrieve(store: VectorStore, question: str, k: int | None = None) -> list[dict]:
    k = k or settings.top_k
    qv = embed_query(question)
    if isinstance(qv, np.ndarray) and qv.ndim == 2:
        qv = qv[0]
    ranked = store.search(qv, k=k)
    results: list[dict] = []
    for score, meta in ranked:
        results.append(
            {
                "score": score,
                "text": meta.get("text", ""),
                "grade": meta.get("grade"),
                "subject_area": meta.get("subject_area"),
                "topic": meta.get("topic"),
                "subtopic": meta.get("subtopic"),
                "document_type": meta.get("document_type"),
                "source_file": meta.get("source_file"),
                "page_start": meta.get("page_start"),
                "page_end": meta.get("page_end"),
            }
        )
    return results


def format_context_for_llm(hits: list[dict]) -> str:
    blocks: list[str] = []
    for i, h in enumerate(hits, start=1):
        header = _source_line(h)
        blocks.append(f"[Context {i}] {header}\n{h.get('text', '').strip()}")
    return "\n\n".join(blocks)


def _source_line(h: dict) -> str:
    parts: list[str] = []
    if h.get("grade") is not None:
        parts.append(f"Grade {h['grade']}")
    if h.get("subject_area"):
        parts.append(str(h["subject_area"]))
    if h.get("topic"):
        parts.append(str(h["topic"]))
    if h.get("subtopic"):
        parts.append(str(h["subtopic"]))
    if h.get("document_type"):
        parts.append(str(h["document_type"]))
    p0, p1 = h.get("page_start"), h.get("page_end")
    if p0 is not None and p1 is not None:
        parts.append(f"pages {p0}-{p1}")
    src = h.get("source_file") or ""
    tail = f" — {src}" if src else ""
    return (" | ".join(parts) if parts else "Source") + tail
