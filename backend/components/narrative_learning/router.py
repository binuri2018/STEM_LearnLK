"""Narrative Learning API: persona theme + textbook RAG story."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.components.narrative_learning.schemas import GenerateRequest, GenerateResponse
from backend.components.narrative_learning.syllabus_data import CHAPTER_MAP

router = APIRouter(prefix="/narrative-learning", tags=["Narrative Learning"])

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from backend.components.narrative_learning.story_engine import StoryEngine

        _engine = StoryEngine()
    return _engine


@router.get("/status")
def status() -> dict:
    from backend.components.narrative_learning.model_config import VECTOR_DB_DIR

    return {
        "status": "ready",
        "module": "Narrative Learning",
        "index_path": VECTOR_DB_DIR,
    }


@router.get("/chapters")
def chapters() -> dict:
    return {"books": CHAPTER_MAP}


@router.post("/generate", response_model=GenerateResponse)
def generate(body: GenerateRequest) -> GenerateResponse:
    try:
        engine = _get_engine()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Narrative engine is not ready: {exc}",
        ) from exc

    theme = engine.get_theme_for_student(body.interest, body.aspiration)
    data = engine.generate_chapter(
        student_theme=theme,
        topic=body.topic,
        diagnostic_query=body.diagnostic,
        interest=body.interest,
        aspiration=body.aspiration,
        struggle_level=body.struggle_level,
        book_name=body.book,
    )
    if not data or not (data.get("story") or "").strip():
        raise HTTPException(status_code=502, detail="Story generation failed. Please try again.")

    return GenerateResponse(
        theme=theme,
        science_intro=data.get("science_intro") or {},
        story=data.get("story") or "",
        key_definitions=data.get("key_definitions") or [],
        key_equations=data.get("key_equations") or [],
        exam_bullets=data.get("exam_bullets") or [],
        quiz_topic=data.get("quiz_topic") or body.topic,
        sources=data.get("sources") or [],
    )
