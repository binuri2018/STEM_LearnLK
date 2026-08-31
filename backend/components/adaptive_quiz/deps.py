"""JWT auth dependency for the Adaptive Quiz component."""
from __future__ import annotations

import secrets
from typing import Annotated

import jwt
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, Header, HTTPException

from backend.common.config import settings
from backend.components.adaptive_quiz.documents import Student
from backend.components.adaptive_quiz.security import decode_token


async def protect(
    authorization: Annotated[str | None, Header()] = None,
) -> Student:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=401,
            detail={"success": False, "message": "Not authorized, no token provided"},
        )

    try:
        oid = decode_token(token)
        student = await Student.get(ObjectId(oid))
    except (jwt.InvalidTokenError, InvalidId, ValueError, KeyError):
        raise HTTPException(
            status_code=401,
            detail={"success": False, "message": "Not authorized, token invalid"},
        )

    if not student:
        raise HTTPException(
            status_code=401,
            detail={"success": False, "message": "Student not found"},
        )

    return student


StudentDep = Annotated[Student, Depends(protect)]


def ensure_owner(claimed_student_id: str, student: Student) -> None:
    """Reject cross-student access: the caller may only act on their own studentId."""
    if claimed_student_id != student.studentId:
        raise HTTPException(
            status_code=403,
            detail={"success": False, "message": "Not authorized for this student"},
        )


async def require_teacher_key(
    x_teacher_key: Annotated[str | None, Header()] = None,
) -> None:
    """Gate teacher-dashboard endpoints with a shared secret — no teacher accounts exist."""
    key = settings.teacher_key
    if not key or not x_teacher_key or not secrets.compare_digest(x_teacher_key, key):
        raise HTTPException(
            status_code=403,
            detail={"success": False, "message": "Invalid or missing teacher key"},
        )


TeacherDep = Annotated[None, Depends(require_teacher_key)]
