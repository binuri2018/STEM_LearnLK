#!/usr/bin/env python3
"""
Sample ingestion: scan Resource/ for PDFs, extract text, chunk, embed, build FAISS.

Recommended folder layout for automatic metadata:
  Resource/grade10/physics/<topic>.pdf
  Resource/grade11/chemistry/...

Then run (from project root):
  python -m venv .venv
  .venv\\Scripts\\activate   # Windows
  pip install -r requirements.txt
  python scripts/ingest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Project root on sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.chunking import Chunk, chunk_pages
from app.config import settings
from app.embeddings import embed_texts_for_ingest
from app.index_manifest import save_manifest
from app.metadata_infer import infer_from_path
from app.pdf_extract import extract_pages
from app.vector_store import VectorStore


def collect_pdfs(resource_dir: Path) -> list[Path]:
    if not resource_dir.is_dir():
        return []
    return sorted(resource_dir.rglob("*.pdf"))


def ingest() -> None:
    resource = settings.resolved_resource_dir()
    data_dir = settings.resolved_data_dir()
    pdfs = collect_pdfs(resource)
    if not pdfs:
        print(f"No PDFs found under {resource}. Add syllabus PDFs and re-run.")
        return

    all_chunks: list[Chunk] = []
    for pdf_path in pdfs:
        meta = infer_from_path(pdf_path.relative_to(resource))
        try:
            pages = extract_pages(pdf_path)
        except Exception as e:
            print(f"Skip {pdf_path}: {e}")
            continue
        rel = str(pdf_path.relative_to(resource)).replace("\\", "/")
        chunks = chunk_pages(
            pages=pages,
            grade=meta.grade,
            subject_area=meta.subject_area,
            topic=meta.topic,
            subtopic=meta.subtopic,
            document_type=meta.document_type,
            source_file=rel,
        )
        all_chunks.extend(chunks)
        print(f"  {rel}: {len(pages)} pages -> {len(chunks)} chunks")

    if not all_chunks:
        print("No chunks produced.")
        return

    texts = [c.text for c in all_chunks]
    prov = settings.embedding_provider
    model_label = (
        settings.openai_embedding_model if prov == "openai" else settings.embedding_model
    )
    print(f"Embedding {len(texts)} chunks via {prov} ({model_label}) …")
    vectors = embed_texts_for_ingest(texts)

    dim = vectors.shape[1]
    store = VectorStore(dim)
    store.add(vectors, all_chunks)
    store.save(data_dir)
    save_manifest(
        data_dir,
        embedding_provider=prov,
        embedding_model=model_label,
        dim=dim,
    )
    print(f"Saved FAISS index, metadata, and index_manifest.json to {data_dir}")


if __name__ == "__main__":
    ingest()
