"""FAISS vector store with JSONL metadata sidecar."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import faiss  # type: ignore
import numpy as np

from backend.common.chunking import Chunk
from backend.common.config import settings


class VectorStore:
    """Inner-product index on L2-normalized embeddings ≈ cosine similarity."""

    def __init__(self, dim: int) -> None:
        self.dim = dim
        self.index = faiss.IndexFlatIP(dim)
        self.metadatas: list[dict] = []

    def add(self, vectors: np.ndarray, chunks: list[Chunk]) -> None:
        if vectors.shape[0] != len(chunks):
            raise ValueError("vectors and chunks length mismatch")
        self.index.add(vectors)
        for c in chunks:
            self.metadatas.append(metadata_dict(c))

    def search(self, query_vec: np.ndarray, k: int) -> list[tuple[float, dict]]:
        if self.index.ntotal == 0:
            return []
        q = query_vec.reshape(1, -1).astype("float32")
        scores, idxs = self.index.search(q, min(k, self.index.ntotal))
        out: list[tuple[float, dict]] = []
        for score, i in zip(scores[0], idxs[0], strict=True):
            if i < 0:
                continue
            out.append((float(score), self.metadatas[i]))
        return out

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(directory / settings.faiss_index_name))
        meta_path = directory / settings.metadata_name
        with meta_path.open("w", encoding="utf-8") as f:
            for row in self.metadatas:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    @classmethod
    def load(cls, directory: Path) -> "VectorStore":
        idx_path = directory / settings.faiss_index_name
        meta_path = directory / settings.metadata_name
        if not idx_path.is_file() or not meta_path.is_file():
            raise FileNotFoundError(f"Missing index or metadata under {directory}")
        index = faiss.read_index(str(idx_path))
        metadatas: list[dict] = []
        with meta_path.open(encoding="utf-8") as f:
            for line in f:
                metadatas.append(json.loads(line))
        store = cls(dim=index.d)
        store.index = index
        store.metadatas = metadatas
        return store


def metadata_dict(c: Chunk) -> dict:
    d = asdict(c)
    return d
