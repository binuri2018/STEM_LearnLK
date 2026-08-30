from typing import Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Student question")
    response_language: Literal["auto", "en", "si"] = Field(
        default="auto",
        description="Answer language: English, Sinhala, or match the question",
    )


class SourceItem(BaseModel):
    score: float | None = None
    grade: int | None = None
    subject_area: str | None = None
    topic: str | None = None
    subtopic: str | None = None
    document_type: str | None = None
    source_file: str | None = None
    page_start: int | None = None
    page_end: int | None = None


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceItem]


class TranscribeResponse(BaseModel):
    text: str


class TtsRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4096)
    voice: str | None = Field(
        default=None,
        description="OpenAI voice: alloy, echo, fable, onyx, nova, shimmer",
    )
