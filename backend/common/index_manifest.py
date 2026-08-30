"""Persist / load embedding backend used to build the FAISS index (must match query time)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.common.config import settings


def manifest_path(data_dir: Path) -> Path:
    return data_dir / settings.index_manifest_name


def save_manifest(
    data_dir: Path,
    *,
    embedding_provider: str,
    embedding_model: str,
    dim: int,
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "dim": dim,
    }
    manifest_path(data_dir).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_manifest(data_dir: Path) -> dict[str, Any] | None:
    p = manifest_path(data_dir)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def resolve_runtime_manifest(store_dim: int, data_dir: Path) -> dict[str, Any]:
    """
    Load manifest from disk, or infer legacy indexes from vector dimension.
    """
    m = load_manifest(data_dir)
    if m is not None:
        if int(m.get("dim", 0)) != store_dim:
            raise ValueError(
                f"Index dimension ({store_dim}) != manifest dim ({m.get('dim')}). "
                "Re-run scripts/ingest.py."
            )
        return m

    if store_dim == 384:
        return {
            "embedding_provider": "local",
            "embedding_model": settings.embedding_model,
            "dim": store_dim,
        }
    if store_dim == 1536:
        return {
            "embedding_provider": "openai",
            "embedding_model": settings.openai_embedding_model,
            "dim": store_dim,
        }
    raise ValueError(
        f"Unknown embedding dimension {store_dim}. Re-run ingest with a supported "
        "embedding provider (local=384, openai text-embedding-3-small=1536)."
    )
