"""Corrected-note orchestrator (Step 7).

Mirrors the spoken student flow exactly:
  1. Verify all claims in the student text against the syllabus.
  2. Split claims into kept (correct / correct_global) and dropped (incorrect / incomplete).
  3. Ask the selected LLM to rewrite a clean note using ONLY the kept claims.

Public API:
  run(text, language, store) -> CorrectNoteResponse
"""
from __future__ import annotations

import logging

from backend.components.knowledge_maps import llm_client
from backend.components.knowledge_maps.prompts import (
    CORRECT_NOTE_TOOL,
    EXTRACT_TAGS_SYSTEM,
    EXTRACT_TAGS_TOOL,
    correct_note_system,
    correct_note_user,
)
from backend.components.knowledge_maps.schemas import Claim, CorrectNoteResponse
from backend.components.knowledge_maps.verification import verify_text
from backend.common.vector_store import VectorStore

logger = logging.getLogger(__name__)


def _rewrite_note(kept: list[Claim], language: str) -> str:
    """Ask the selected LLM to produce a clean note from kept claims."""
    claim_texts = [
        c.corrected_version if c.corrected_version else c.claim
        for c in kept
    ]
    if not claim_texts:
        return "No verified-correct claims found — the note could not be regenerated."

    messages = [
        {"role": "system", "content": correct_note_system(language)},
        {"role": "user", "content": correct_note_user(claim_texts)},
    ]
    result = llm_client.chat_with_tools(
        messages=messages,
        tools=[CORRECT_NOTE_TOOL],
        tool_choice={"type": "function", "function": {"name": "submit_corrected_note"}},
        temperature=0.2,
    )
    return result.get("corrected_note", "").strip()


def _extract_tags(note_text: str) -> list[str]:
    """Extract 3–6 searchable topic tags via structured LLM output."""
    messages = [
        {"role": "system", "content": EXTRACT_TAGS_SYSTEM},
        {"role": "user", "content": note_text},
    ]
    result = llm_client.chat_with_tools(
        messages=messages,
        tools=[EXTRACT_TAGS_TOOL],
        tool_choice={"type": "function", "function": {"name": "submit_tags"}},
        temperature=0.2,
    )
    return result.get("tags", [])


def run(
    text: str,
    language: str,
    store: VectorStore,
) -> CorrectNoteResponse:
    """Full orchestration: verify → split → rewrite.

    Raises:
      RuntimeError — LLM provider not configured
      HTTPException (503) — store not loaded (raised by caller via _get_store)
    """
    verification = verify_text(text, store, language)

    kept: list[Claim] = [
        c for c in verification.claims
        if c.verdict == "correct" and c.evidence_status == "cited"
    ]
    dropped: list[Claim] = [
        c for c in verification.claims if c.verdict in {"incorrect", "incomplete"}
    ]
    unresolved: list[Claim] = [
        c for c in verification.claims
        if c.verdict in {"insufficient_evidence", "verification_failed"}
    ]

    if kept:
        corrected_note = _rewrite_note(kept, language)
    else:
        corrected_note = (
            "No claims could be verified as correct against the syllabus. "
            "Please review your notes and try again."
        )

    tags: list[str] = []
    if corrected_note and kept:
        try:
            tags = _extract_tags(corrected_note)
        except Exception:
            logger.warning("Tag extraction failed — returning empty tags", exc_info=True)

    return CorrectNoteResponse(
        original_text=text,
        verification=verification,
        corrected_note=corrected_note,
        kept_claims=kept,
        dropped_claims=dropped,
        unresolved_claims=unresolved,
        tags=tags,
    )
