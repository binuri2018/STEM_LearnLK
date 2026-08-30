"""Adaptive Quiz component router."""
from fastapi import APIRouter

router = APIRouter(prefix="/adaptive-quiz", tags=["Adaptive Quiz"])


@router.get("/status")
def status() -> dict:
    return {"status": "coming_soon", "module": "Adaptive Quiz"}
