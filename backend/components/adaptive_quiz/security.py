"""Password hashing, JWT tokens, and Mongoose-style JSON serialisation."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from backend.common.config import settings


def hash_password(plain: str) -> str:
    # Native bcrypt; passlib+bcrypt>=5 rejects short passwords with a bogus 72-byte error.
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


def generate_token(student_id: str) -> str:
    exp = datetime.now(UTC) + timedelta(days=settings.jwt_expire_days)
    return jwt.encode({"id": student_id, "exp": exp}, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> str:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    return str(payload["id"])


def document_legacy(doc: Any) -> dict[str, Any]:
    """Match Mongoose-ish JSON: ``_id`` string, camelCase keys as on the model."""
    raw = doc.model_dump(mode="python")
    oid = getattr(doc, "id", None)
    if oid is not None:
        raw["_id"] = str(oid)
    raw.pop("id", None)
    return raw
