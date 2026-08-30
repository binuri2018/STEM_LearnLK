"""
Extract plain text from PDFs using PyMuPDF (fitz).
Returns a list of per-page strings to preserve rough structure for chunking.
"""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF


def extract_pages(pdf_path: Path) -> list[str]:
    """Return cleaned text for each page."""
    path = Path(pdf_path)
    doc = fitz.open(path)
    pages: list[str] = []
    try:
        for i in range(len(doc)):
            page = doc.load_page(i)
            text = page.get_text("text") or ""
            pages.append(normalize_whitespace(text))
    finally:
        doc.close()
    return pages


def normalize_whitespace(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)
