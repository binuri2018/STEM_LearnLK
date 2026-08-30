"""FastAPI app: AI STEM Ecosystem API under /api, frontend UI under /."""
from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.common.config import settings
from backend.common.embeddings import (
    EmbeddingLoadError,
    configure_embeddings,
    warm_local_embedding_model,
)
from backend.common.index_manifest import resolve_runtime_manifest
from backend.common.vector_store import VectorStore
from backend.components.adaptive_quiz import adaptive_quiz_router
from backend.components.knowledge_maps import knowledge_maps_router
from backend.components.narrative_learning import narrative_learning_router
from backend.components.voice_tutor.router import (
    router as voice_tutor_router,
    set_store_getter,
)

logger = logging.getLogger(__name__)

_store: VectorStore | None = None


def get_store() -> VectorStore:
    if _store is None:
        raise HTTPException(
            status_code=503,
            detail="Vector index not loaded. Run scripts/ingest.py after adding PDFs to Resource/.",
        )
    return _store


set_store_getter(get_store)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _store
    data_dir = settings.resolved_data_dir()
    _store = None
    configure_embeddings(None)
    try:
        loaded = VectorStore.load(data_dir)
    except FileNotFoundError:
        pass
    else:
        man = resolve_runtime_manifest(loaded.index.d, data_dir)
        configure_embeddings(man)
        _store = loaded
        if man.get("embedding_provider") != "openai":
            try:
                warm_local_embedding_model()
            except EmbeddingLoadError as exc:
                logger.warning("Local embeddings not ready: %s", exc)
    yield
    _store = None
    configure_embeddings(None)


app = FastAPI(
    title="Sri Lanka G10–11 Science AI STEM Ecosystem",
    lifespan=lifespan,
)


@app.get("/api/health")
def health() -> dict:
    data_dir = settings.resolved_data_dir()
    ok = _store is not None and (data_dir / settings.faiss_index_name).is_file()
    return {
        "status": "ok" if ok else "degraded",
        "index_loaded": ok,
        "openai_configured": bool(settings.openai_api_key and settings.openai_api_key.strip()),
    }


# Include component routers under /api
app.include_router(voice_tutor_router, prefix="/api")
app.include_router(voice_tutor_router, prefix="/api/voice-tutor")
# Legacy endpoint support
app.include_router(voice_tutor_router, prefix="", include_in_schema=False)

app.include_router(narrative_learning_router, prefix="/api")
app.include_router(adaptive_quiz_router, prefix="/api")
app.include_router(knowledge_maps_router, prefix="/api")

# Static frontend serving
_frontend_dir = settings.resolved_frontend_dir()


def _serve_frontend_page(subpath: str) -> FileResponse:
    target = _frontend_dir / subpath / "index.html"
    if not target.is_file():
        # Fallback to home or root index.html
        target = _frontend_dir / "home" / "index.html"
    if not target.is_file():
        target = _frontend_dir / "index.html"
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"Page not found: {subpath}")
    return FileResponse(target)


@app.get("/", include_in_schema=False)
def serve_root() -> FileResponse:
    return _serve_frontend_page("home")


@app.get("/home", include_in_schema=False)
@app.get("/home/", include_in_schema=False)
def serve_home() -> FileResponse:
    return _serve_frontend_page("home")


@app.get("/voice-tutor", include_in_schema=False)
@app.get("/voice-tutor/", include_in_schema=False)
def serve_voice() -> FileResponse:
    return _serve_frontend_page("voice_tutor")


@app.get("/narrative-learning", include_in_schema=False)
@app.get("/narrative-learning/", include_in_schema=False)
def serve_narrative() -> FileResponse:
    return _serve_frontend_page("narrative_learning")


@app.get("/adaptive-quiz", include_in_schema=False)
@app.get("/adaptive-quiz/", include_in_schema=False)
def serve_quiz() -> FileResponse:
    return _serve_frontend_page("adaptive_quiz")


@app.get("/knowledge-maps", include_in_schema=False)
@app.get("/knowledge-maps/", include_in_schema=False)
def serve_maps() -> FileResponse:
    return _serve_frontend_page("knowledge_maps")


if _frontend_dir.is_dir():
    app.mount(
        "/static",
        StaticFiles(directory=str(_frontend_dir)),
        name="frontend-static",
    )
