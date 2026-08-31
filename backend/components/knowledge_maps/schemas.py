"""Pydantic schemas for Member 4 endpoints.

This file grows as features are added (OCR, verify, synthesize, YouTube,
correct-note, suggestions).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ─── Health ────────────────────────────────────────────────────────────────


class M4HealthResponse(BaseModel):
    llm_provider: Literal["ollama", "azure"]
    llm_configured: bool
    llm_ok: bool
    llm_model: str | None = None
    llm_latency_ms: int | None = None
    llm_error: str | None = None
    youtube_api_configured: bool
    index_loaded: bool
    retrieval_method: str = "hybrid_rrf"
    retriever_signature: str | None = None
    reranker_model: str | None = None
    reranker_revision: str | None = None
    reranker_loaded: bool = False
    reranker_error: str | None = None


# ─── Synthesis ─────────────────────────────────────────────────────────────


SynthesisMode = Literal["flashcards", "mindmap", "notes"]
LangMode = Literal["en", "si", "auto"]


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000, description="Source text to synthesise.")
    mode: SynthesisMode = Field(..., description="flashcards | mindmap | notes")
    language: LangMode = Field(default="auto")


class Flashcard(BaseModel):
    front: str
    back: str


class FlashcardsResponse(BaseModel):
    flashcards: list[Flashcard]


class MindMapNode(BaseModel):
    id: str
    label: str
    group: str = "default"
    importance: float = 0.5
    parent: str | None = None  # id of this node's parent in the radial tree; None for the root


class MindMapEdge(BaseModel):
    source: str
    target: str
    relation: str = ""


class MindMapResponse(BaseModel):
    root: str | None = None  # id of the central topic; None only when there are no nodes
    nodes: list[MindMapNode]
    edges: list[MindMapEdge]  # cross-links only — the parent backbone lives on the nodes


class NotesSection(BaseModel):
    heading: str
    bullets: list[str]
    key_terms: list[str] = []


class NotesResponse(BaseModel):
    sections: list[NotesSection]


# ─── Verification ──────────────────────────────────────────────────────────


class VerifyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    response_language: LangMode = Field(default="auto")


class EvidenceItem(BaseModel):
    evidence_id: str
    source_type: Literal["syllabus", "web"]
    relation: Literal["supports", "refutes", "context"]
    title: str
    excerpt: str
    url: str
    document_id: str | None = None
    pdf_page_start: int | None = None
    pdf_page_end: int | None = None
    grade: int | None = None
    topic: str | None = None
    subtopic: str | None = None
    document_type: str | None = None
    retrieval_score: float | None = None
    domain: str | None = None
    retrieval_method: str | None = None
    dense_score: float | None = None
    keyword_score: float | None = None
    fusion_score: float | None = None
    reranker_score: float | None = None


class ConfidenceInfo(BaseModel):
    status: Literal["provisional", "calibrated", "unavailable"] = "unavailable"
    level: Literal["low", "medium", "high", "unavailable"] = "unavailable"
    probability: float | None = Field(default=None, ge=0.0, le=1.0)
    method: str | None = None
    reasons: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    claim: str
    claim_id: str | None = None
    source_block_id: str | None = None
    source_start: int | None = Field(default=None, ge=0)
    source_end: int | None = Field(default=None, ge=0)
    verdict: Literal[
        "correct", "incorrect", "incomplete", "insufficient_evidence", "verification_failed"
    ]
    explanation: str
    corrected_version: str | None = None
    memory_tip: str | None = None
    source: Literal["syllabus", "web", "none"] = "syllabus"
    evidence_status: Literal["cited", "not_found", "unavailable"] = "unavailable"
    evidence: list[EvidenceItem] = Field(default_factory=list)
    confidence: ConfidenceInfo = Field(default_factory=ConfidenceInfo)


class ScoreSummary(BaseModel):
    total_claims: int
    decidable_claims: int
    correct: int
    incorrect: int
    incomplete: int
    insufficient_evidence: int
    verification_failed: int
    coverage: float = Field(ge=0.0, le=1.0)


class VerifyResponse(BaseModel):
    overall_score: float | None
    score_summary: ScoreSummary
    claims: list[Claim]


# ─── YouTube ───────────────────────────────────────────────────────────────


class YoutubeRequest(BaseModel):
    url: str = Field(..., min_length=10)
    language: LangMode = Field(default="auto")


class YoutubeResponse(BaseModel):
    transcript_excerpt: str
    verification: VerifyResponse
    notes: dict        # {"sections": [...]}  — renderStructuredNotes
    flashcards: list[Flashcard]
    mind_map: dict     # {"nodes": [...], "edges": [...]}  — renderMindMap


# ─── YouTube Suggestions ───────────────────────────────────────────────────


class YoutubeSuggestRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=200)
    max_results: int = Field(default=6, ge=1, le=12)


class YoutubeVideoCard(BaseModel):
    title: str
    url: str
    thumbnail: str
    channel: str


class YoutubeSuggestResponse(BaseModel):
    videos: list[YoutubeVideoCard]


# ─── Corrected Note ────────────────────────────────────────────────────────


class CorrectNoteRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    response_language: LangMode = Field(default="auto")


class CorrectNoteResponse(BaseModel):
    original_text: str
    verification: VerifyResponse
    corrected_note: str          # clean rewritten note — only correct claims
    kept_claims: list[Claim]     # correct + correct_global (source=web)
    dropped_claims: list[Claim]  # incorrect / incomplete
    unresolved_claims: list[Claim] = Field(default_factory=list)
    tags: list[str] = []         # auto-extracted topic tags for YouTube search


# ─── Repair and re-verification ───────────────────────────────────────────


class RepairNoteRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    response_language: LangMode = Field(default="auto")
    preserve_structure: bool = True


class NoteBlock(BaseModel):
    block_id: str
    block_type: Literal["heading", "paragraph", "list_item", "blank"]
    original_text: str
    final_text: str | None = None
    marker: str = ""
    status: Literal["unchanged", "repaired", "unresolved", "excluded"] = "unchanged"
    repair_ids: list[str] = Field(default_factory=list)


class RepairRecord(BaseModel):
    repair_id: str
    claim_id: str
    block_id: str
    source_fragment: str
    block_start: int | None = Field(default=None, ge=0)
    block_end: int | None = Field(default=None, ge=0)
    original_claim: str
    proposed_claim: str | None = None
    repair_status: Literal["not_needed", "repaired", "unresolved", "failed"]
    unresolved_reason: Literal[
        "insufficient_evidence",
        "invalid_span",
        "invalid_proposal",
        "second_verdict_not_correct",
        "service_failure",
    ] | None = None
    first_verdict: Literal[
        "correct", "incorrect", "incomplete", "insufficient_evidence", "verification_failed"
    ]
    second_verdict: Literal[
        "correct", "incorrect", "incomplete", "insufficient_evidence", "verification_failed"
    ] | None = None
    change_reason: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    confidence: ConfidenceInfo | None = None
    included_by_default: bool = False


class RepairNoteResponse(BaseModel):
    original_text: str
    verification: VerifyResponse
    repaired_note: str
    blocks: list[NoteBlock]
    repairs: list[RepairRecord]
    unresolved_claims: list[Claim] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


# ─── Video Summary ─────────────────────────────────────────────────────────


class VideoSummaryRequest(BaseModel):
    url: str = Field(..., min_length=10)
    language: LangMode = Field(default="auto")


class VideoSummaryResponse(BaseModel):
    summary: str
    key_points: list[str]
    title: str = ""


# ─── OCR ───────────────────────────────────────────────────────────────────


class OcrResponse(BaseModel):
    text: str
    # Frontend (web/app.js:321) reassigns the preview <img>.src if present.
    # We don't use cloud storage, so this stays None — kept for shape compat.
    signed_url: str | None = None


class OcrRegion(BaseModel):
    region_id: str
    region_type: Literal["paragraph", "table", "equation", "label", "diagram"]
    text: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reading_order: int = Field(ge=1)
    warnings: list[str] = Field(default_factory=list)


class OcrReviewItem(BaseModel):
    review_id: str
    source_text: str
    suggested_text: str
    reason: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    category: Literal["formula", "terminology", "spelling", "unclear"]


class OcrPreprocessingInfo(BaseModel):
    orientation_corrected: bool = False
    contrast_enhanced: bool = False
    margins_cropped: bool = False


class OcrReviewResponse(BaseModel):
    text: str
    review_status: Literal["needs_review", "ready", "unavailable"]
    overall_confidence: Literal["low", "medium", "high", "unavailable"]
    regions: list[OcrRegion] = Field(default_factory=list)
    review_items: list[OcrReviewItem] = Field(default_factory=list)
    preprocessing: OcrPreprocessingInfo = Field(default_factory=OcrPreprocessingInfo)
    retention: str = "Image processed in memory and discarded after this request."
