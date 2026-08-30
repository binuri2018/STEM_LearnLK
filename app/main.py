"""FastAPI app: syllabus RAG API under /api, static student UI under /."""
from __future__ import annotations

from contextlib import asynccontextmanager
import logging

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.audio_services import synthesize_speech, transcribe_bytes
from app.config import settings
from app.embeddings import (
    EmbeddingLoadError,
    configure_embeddings,
    warm_local_embedding_model,
)
from app.index_manifest import resolve_runtime_manifest
from app.llm import answer_question
from app.retrieval import format_context_for_llm, retrieve
from app.schemas import (
    AskRequest,
    AskResponse,
    SourceItem,
    TranscribeResponse,
    TtsRequest,
)
from app.vector_store import VectorStore

logger = logging.getLogger(__name__)

_store: VectorStore | None = None


def _llm_connection_detail(exc: httpx.HTTPError) -> str:
    """Turn low-level refused-connection errors into actionable hints."""
    raw = f"{type(exc).__name__}: {exc!s}"
    using_openai = bool(settings.openai_api_key and settings.openai_api_key.strip())
    if using_openai:
        return (
            f"OpenAI request failed ({raw}). Check internet, VPN, firewall, and OPENAI_API_KEY."
        )
    refused = (
        "10061" in raw
        or "actively refused" in raw.lower()
        or isinstance(exc, httpx.ConnectError)
    )
    if refused:
        m = settings.ollama_chat_model
        return (
            "No chat model reachable: Ollama is not accepting connections at "
            f"{settings.ollama_base_url}. Install/start Ollama, then run "
            f"`ollama pull {m}`, or set OPENAI_API_KEY in .env to use OpenAI instead of Ollama. "
            f"(Detail: {raw})"
        )
    return f"LLM backend request failed: {raw}"


def get_store() -> VectorStore:
    if _store is None:
        raise HTTPException(
            status_code=503,
            detail="Vector index not loaded. Run scripts/ingest.py after adding PDFs to Resource/.",
        )
    return _store


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
    title="Sri Lanka G10–11 Science RAG Tutor",
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


@app.post("/ask", response_model=AskResponse, include_in_schema=False)
@app.post("/api/ask", response_model=AskResponse)
def ask(body: AskRequest) -> AskResponse:
    store = get_store()
    try:
        hits = retrieve(store, body.question.strip())
    except EmbeddingLoadError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not hits:
        lang = (body.response_language or "auto").lower()
        from app.llm import REFUSAL_EN, REFUSAL_SI

        msg = REFUSAL_SI if lang == "si" else REFUSAL_EN
        return AskResponse(answer=msg, sources=[])

    context = format_context_for_llm(hits)
    try:
        answer = answer_question(
            context,
            body.question.strip(),
            response_language=body.response_language,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=_llm_connection_detail(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"LLM error: {exc!s}",
        ) from exc
    sources = [
        SourceItem(
            score=h.get("score"),
            grade=h.get("grade"),
            subject_area=h.get("subject_area"),
            topic=h.get("topic"),
            subtopic=h.get("subtopic"),
            document_type=h.get("document_type"),
            source_file=h.get("source_file"),
            page_start=h.get("page_start"),
            page_end=h.get("page_end"),
        )
        for h in hits
    ]
    return AskResponse(answer=answer, sources=sources)


@app.post("/api/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(file: UploadFile = File(...)) -> TranscribeResponse:
    try:
        data = await file.read()
        text = transcribe_bytes(data, file.filename or "audio.webm")
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Transcription failed: {exc!s}",
        ) from exc
    return TranscribeResponse(text=text)


@app.post("/api/tts")
async def tts_endpoint(body: TtsRequest) -> Response:
    try:
        audio = synthesize_speech(body.text, body.voice)
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"TTS failed: {exc!s}",
        ) from exc
    return Response(content=audio, media_type="audio/mpeg")


_web_dir = settings.project_root / "web"


@app.get("/", include_in_schema=False)
def serve_student_ui() -> FileResponse:
    index = _web_dir / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="web/index.html not found.")
    return FileResponse(index)


if _web_dir.is_dir():
    app.mount(
        "/static",
        StaticFiles(directory=str(_web_dir)),
        name="web-static",
    )
