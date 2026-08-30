"""Narrative Learning component router."""
from fastapi import APIRouter

router = APIRouter(prefix="/narrative-learning", tags=["Narrative Learning"])


@router.get("/status")
def status() -> dict:
    return {"status": "coming_soon", "module": "Narrative Learning"}
