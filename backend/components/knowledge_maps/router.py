"""Knowledge Maps component router."""
from fastapi import APIRouter

router = APIRouter(prefix="/knowledge-maps", tags=["Knowledge Maps"])


@router.get("/status")
def status() -> dict:
    return {"status": "coming_soon", "module": "Knowledge Maps"}
