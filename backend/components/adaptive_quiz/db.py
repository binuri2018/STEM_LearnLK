"""MongoDB (Motor + Beanie) connection for the Adaptive Quiz component.

Isolated from the rest of the app: if ``MONGO_URI`` is unset or the connection
fails, only quiz endpoints are affected — the RAG store and other components
continue to work.
"""
from __future__ import annotations

import logging

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from backend.common.config import settings
from backend.components.adaptive_quiz.documents import ALL_DOCUMENTS

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_ready: bool = False


async def init_quiz_db() -> None:
    """Connect and register Beanie models. Raises if MONGO_URI is missing."""
    global _client, _ready
    if _ready:
        return
    if not settings.mongo_uri:
        raise RuntimeError("MONGO_URI is not set")

    _client = AsyncIOMotorClient(settings.mongo_uri)
    db = _client.get_default_database()
    await init_beanie(database=db, document_models=ALL_DOCUMENTS)
    _ready = True
    logger.info("Adaptive Quiz MongoDB connected (Beanie initialised)")


async def close_quiz_db() -> None:
    global _client, _ready
    if _client is not None:
        _client.close()
        _client = None
    _ready = False


def quiz_db_ready() -> bool:
    return _ready
