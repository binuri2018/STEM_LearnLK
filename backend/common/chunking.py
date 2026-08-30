"""
Semantic-ish chunking: target 200–400 words per chunk.
Splits on paragraphs first, then sentences for oversized blocks.

Metadata (grade, subject_area, topic) is supplied by the ingest pipeline
(path/filename conventions or manual labels).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from backend.common.config import settings


@dataclass
class Chunk:
    text: str
    grade: int | None
    subject_area: str | None  # Physics | Chemistry | Biology | Science
    topic: str | None
    subtopic: str | None
    document_type: str | None  # Teacher's Guide vs Syllabus & learner material
    source_file: str
    page_start: int | None
    page_end: int | None


def chunk_document(
    *,
    full_text: str,
    grade: int | None,
    subject_area: str | None,
    topic: str | None,
    subtopic: str | None,
    document_type: str | None,
    source_file: str,
) -> list[Chunk]:
    """Chunk a full document string (no per-page provenance)."""
    return _chunk_plain_text(
        full_text.strip(),
        grade=grade,
        subject_area=subject_area,
        topic=topic,
        subtopic=subtopic,
        document_type=document_type,
        source_file=source_file,
        page_start=None,
        page_end=None,
    )


def chunk_pages(
    *,
    pages: list[str],
    grade: int | None,
    subject_area: str | None,
    topic: str | None,
    subtopic: str | None,
    document_type: str | None,
    source_file: str,
    page_offset: int = 1,
) -> list[Chunk]:
    """Chunk each PDF page separately so page numbers align with the syllabus PDF."""
    chunks: list[Chunk] = []
    for idx, text in enumerate(pages):
        pnum = page_offset + idx
        page_chunks = _chunk_plain_text(
            text.strip(),
            grade=grade,
            subject_area=subject_area,
            topic=topic,
            subtopic=subtopic,
            document_type=document_type,
            source_file=source_file,
            page_start=pnum,
            page_end=pnum,
        )
        chunks.extend(page_chunks)
    return chunks


def _chunk_plain_text(
    text: str,
    *,
    grade: int | None,
    subject_area: str | None,
    topic: str | None,
    subtopic: str | None,
    document_type: str | None,
    source_file: str,
    page_start: int | None,
    page_end: int | None,
) -> list[Chunk]:
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks_out: list[Chunk] = []
    bucket: list[str] = []
    bucket_words = 0

    def flush() -> None:
        nonlocal bucket, bucket_words
        if not bucket:
            return
        body = "\n\n".join(bucket)
        chunks_out.append(
            Chunk(
                text=body,
                grade=grade,
                subject_area=subject_area,
                topic=topic,
                subtopic=subtopic,
                document_type=document_type,
                source_file=source_file,
                page_start=page_start,
                page_end=page_end,
            )
        )
        bucket = []
        bucket_words = 0

    for para in paragraphs:
        pw = word_count(para)

        if pw > settings.chunk_max_words:
            flush()
            for piece in split_oversized_paragraph(para):
                chunks_out.append(
                    Chunk(
                        text=piece,
                        grade=grade,
                        subject_area=subject_area,
                        topic=topic,
                        subtopic=subtopic,
                        document_type=document_type,
                        source_file=source_file,
                        page_start=page_start,
                        page_end=page_end,
                    )
                )
            continue

        if bucket_words + pw > settings.chunk_max_words and bucket_words > 0:
            flush()

        bucket.append(para)
        bucket_words += pw

        if bucket_words >= settings.chunk_min_words:
            flush()

    flush()
    return chunks_out


def word_count(s: str) -> int:
    return len(re.findall(r"\w+", s, flags=re.UNICODE))


_SENT_SPLIT = re.compile(r"(?<=[.?!])\s+")


def split_oversized_paragraph(para: str) -> list[str]:
    """Split long paragraph into segments of at most chunk_max_words."""
    sentences = [s.strip() for s in _SENT_SPLIT.split(para) if s.strip()]
    if len(sentences) <= 1:
        return hard_split_words(para, settings.chunk_max_words)

    out: list[str] = []
    bucket: list[str] = []
    bw = 0
    for sent in sentences:
        sw = word_count(sent)
        if sw > settings.chunk_max_words:
            if bucket:
                out.append(" ".join(bucket))
                bucket = []
                bw = 0
            out.extend(hard_split_words(sent, settings.chunk_max_words))
            continue
        if bw + sw > settings.chunk_max_words and bw > 0:
            out.append(" ".join(bucket))
            bucket = []
            bw = 0
        bucket.append(sent)
        bw += sw
    if bucket:
        out.append(" ".join(bucket))
    return out


def hard_split_words(text: str, max_words: int) -> list[str]:
    words = re.findall(r"\S+", text)
    if not words:
        return []
    batches: list[str] = []
    for i in range(0, len(words), max_words):
        batches.append(" ".join(words[i : i + max_words]))
    return batches
