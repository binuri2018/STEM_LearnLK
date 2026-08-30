from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    interest: str = Field(min_length=1)
    aspiration: str = Field(min_length=1)
    struggle_level: str = "Medium"
    book: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    diagnostic: str = "Explain the core concept in simple terms."


class GenerateResponse(BaseModel):
    theme: str
    science_intro: dict[str, Any] = Field(default_factory=dict)
    story: str = ""
    key_definitions: list[dict[str, Any]] = Field(default_factory=list)
    key_equations: list[dict[str, Any]] = Field(default_factory=list)
    exam_bullets: list[str] = Field(default_factory=list)
    quiz_topic: str = ""
    sources: list[dict[str, Any]] = Field(default_factory=list)
