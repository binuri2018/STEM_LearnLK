"""
Infer grade, subject, topic, and document type from folder path and filename.

Supports common Sri Lanka MOE-style names, e.g.:
  science Grade 10 Part 1.pdf
  Teacher's Guide Grade 10.pdf
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_SUBJECT_ALIASES = {
    "physics": "Physics",
    "chem": "Chemistry",
    "chemistry": "Chemistry",
    "bio": "Biology",
    "biology": "Biology",
}

DOC_TEACHER = "Teacher's Guide"
DOC_SYLLABUS = "Syllabus & learner material"


@dataclass
class PdfMetadata:
    grade: int | None
    subject_area: str | None
    topic: str | None
    subtopic: str | None
    document_type: str | None


def infer_from_path(relative_pdf: Path) -> PdfMetadata:
    parts = [x.lower() for x in relative_pdf.parts]
    stem_raw = relative_pdf.stem.strip()
    name = stem_raw.replace("_", " ").strip()
    name_lower = name.lower()
    haystack = " ".join(parts) + " " + name_lower

    grade = _parse_grade(parts, name_lower)
    document_type = _parse_document_type(name_lower)
    subject = _parse_subject(haystack, name_lower)
    subtopic = _parse_part_subtopic(name_lower)

    topic = stem_raw if stem_raw else None
    if document_type == DOC_TEACHER and grade is not None:
        topic = f"Teacher's Guide · Grade {grade}"
    elif document_type == DOC_SYLLABUS and grade is not None and "science" in name_lower:
        topic = f"Science · Grade {grade}" + (f" · {subtopic}" if subtopic else "")

    return PdfMetadata(
        grade=grade,
        subject_area=(
            subject
            or ("Science" if ("science" in name_lower or document_type == DOC_TEACHER) else None)
        ),
        topic=topic,
        subtopic=subtopic,
        document_type=document_type,
    )


def _parse_grade(parts: list[str], name_lower: str) -> int | None:
    for part in parts:
        g = _grade_from_text(part)
        if g is not None:
            return g
    return _grade_from_text(name_lower)


def _grade_from_text(text: str) -> int | None:
    m = re.search(r"grade\s*[_-]?\s*(10|11)", text, re.I) or re.search(
        r"grade(10|11)\b", text, re.I
    )
    if m:
        return int(m.group(1))
    m = re.search(r"\bg[-\s]?(10|11)\b", text, re.I)
    if m:
        return int(m.group(1))
    if re.fullmatch(r"10|11", text):
        return int(text)
    return None


def _parse_document_type(name_lower: str) -> str | None:
    if re.search(r"teacher['\u2019s]{0,2}\s*guide", name_lower):
        return DOC_TEACHER
    if "science" in name_lower and re.search(r"\bgrade\s*(10|11)\b", name_lower):
        return DOC_SYLLABUS
    if re.search(r"\bpart\s*\d+", name_lower) and "science" in name_lower:
        return DOC_SYLLABUS
    return None


def _parse_subject(haystack: str, name_lower: str) -> str | None:
    for key, label in _SUBJECT_ALIASES.items():
        if key in haystack:
            return label
    for key, label in _SUBJECT_ALIASES.items():
        if key in name_lower:
            return label
    return None


def _parse_part_subtopic(name_lower: str) -> str | None:
    m = re.search(r"\bpart\s*(\d+)\b", name_lower, re.I)
    if m:
        return f"Part {m.group(1)}"
    return None
