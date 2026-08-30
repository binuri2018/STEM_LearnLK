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


class ImageItem(BaseModel):
    """A textbook figure retrieved alongside the text answer."""
    image_id: str
    url: str
    source: str
    page: int
    caption: str = ""


class VisualItem(BaseModel):
    """An internet-retrieved educational visual explanation diagram."""
    image_url: str
    title: str
    source_name: str
    source_url: str
    search_query: str
    relevance_score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
    images: list[ImageItem] = []  # Local textbook figures
    visual_required: bool = False  # Whether visual explanation was recommended & found
    visual: VisualItem | None = None  # Selected online visual explanation diagram


class TranscribeResponse(BaseModel):
    text: str


class TtsRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4096)
    voice: str | None = Field(
        default=None,
        description="OpenAI voice: alloy, echo, fable, onyx, nova, shimmer",
    )
