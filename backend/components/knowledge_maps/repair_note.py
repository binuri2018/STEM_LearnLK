"""Structure-preserving, evidence-constrained note repair and re-verification."""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

from backend.components.knowledge_maps import llm_client
from backend.components.knowledge_maps.concurrency import run_concurrent
from backend.components.knowledge_maps.correct_note import _extract_tags
from backend.components.knowledge_maps.prompts import (
    REPAIR_CLAIM_SYSTEM,
    REPAIR_CLAIM_TOOL,
    STRUCTURED_CLAIM_EXTRACTION_SYSTEM,
    STRUCTURED_CLAIM_EXTRACTION_TOOL,
    language_instruction,
)
from backend.components.knowledge_maps.schemas import (
    Claim,
    NoteBlock,
    RepairNoteResponse,
    RepairRecord,
)
from backend.components.knowledge_maps.verification import response_for_claims, verify_claims
from backend.common.vector_store import VectorStore

logger = logging.getLogger(__name__)

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+")
_LIST = re.compile(r"^(\s*(?:[-*+]\s+|\d+[.)]\s+))")


@dataclass(frozen=True)
class ParsedBlock:
    block_id: str
    block_type: str
    original_text: str
    marker: str
    source_offset: int


def _is_heading(line: str) -> bool:
    body = line.rstrip("\r\n")
    stripped = body.strip()
    return bool(
        _HEADING.match(body)
        or (stripped.endswith(":") and len(stripped.split()) <= 12)
        or (stripped.isupper() and 0 < len(stripped.split()) <= 12)
    )


def parse_note_blocks(text: str) -> list[ParsedBlock]:
    """Split text into ordered blocks while retaining every original character."""
    lines = str(text).splitlines(keepends=True)
    if not lines and text:
        lines = [text]
    blocks: list[ParsedBlock] = []
    offset = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            body, kind, marker = line, "blank", ""
            index += 1
        else:
            list_match = _LIST.match(line)
            if list_match:
                body, kind, marker = line, "list_item", list_match.group(1)
                index += 1
            elif _is_heading(line):
                heading_match = _HEADING.match(line)
                body, kind = line, "heading"
                marker = heading_match.group(0) if heading_match else ""
                index += 1
            else:
                paragraph = [line]
                index += 1
                while index < len(lines):
                    candidate = lines[index]
                    if not candidate.strip() or _LIST.match(candidate) or _is_heading(candidate):
                        break
                    paragraph.append(candidate)
                    index += 1
                body, kind, marker = "".join(paragraph), "paragraph", ""
        blocks.append(ParsedBlock(f"B{len(blocks) + 1}", kind, body, marker, offset))
        offset += len(body)
    return blocks


def _normalize_with_map(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Return (normalised text, per-char raw spans).

    ``raw_spans[i]`` is the half-open slice of ``text`` that produced ``norm[i]``.
    A normalised hit ``norm[a:b]`` therefore maps back to the raw slice
    ``text[raw_spans[a][0] : raw_spans[b - 1][1]]``. Whitespace runs collapse to a
    single space; every other char is NFKC-normalised, any Unicode dash folds to
    ``-``, then casefolded.
    """
    norm_chars: list[str] = []
    raw_spans: list[tuple[int, int]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            j = i + 1
            while j < n and text[j].isspace():
                j += 1
            norm_chars.append(" ")
            raw_spans.append((i, j))
            i = j
            continue
        base = unicodedata.normalize("NFKC", ch)
        if len(base) == 1 and unicodedata.category(base) == "Pd":
            base = "-"
        for folded in base.casefold():
            norm_chars.append(folded)
            raw_spans.append((i, i + 1))
        i += 1
    return "".join(norm_chars), raw_spans


def _unique_find(haystack: str, needle: str) -> int | None:
    if not needle:
        return None
    first = haystack.find(needle)
    if first < 0 or haystack.find(needle, first + 1) >= 0:
        return None
    return first


def _locate_normalized(raw: str, fragment: str) -> tuple[int, int] | None:
    norm_hay, spans = _normalize_with_map(raw)
    norm_needle = _normalize_with_map(fragment)[0].strip()
    hit = _unique_find(norm_hay, norm_needle)
    if hit is None:
        return None
    start = spans[hit][0]
    end = spans[hit + len(norm_needle) - 1][1]
    while start < end and raw[start].isspace():
        start += 1
    while end > start and raw[end - 1].isspace():
        end -= 1
    return (start, end) if end > start else None


def locate_source_fragment(block: ParsedBlock | None, fragment: str) -> tuple[int, int] | None:
    if block is None or not fragment:
        return None
    raw = block.original_text
    start = raw.find(fragment)
    if start >= 0:
        # Exact match: keep the historic "unique substring or nothing" contract.
        return None if raw.find(fragment, start + 1) >= 0 else (start, start + len(fragment))
    return _locate_normalized(raw, fragment)


def reject_overlapping_spans(spans: list[tuple[int, int]]) -> list[bool]:
    valid = [start >= 0 and end > start for start, end in spans]
    for left, (start, end) in enumerate(spans):
        for right, (other_start, other_end) in enumerate(spans):
            if left == right:
                continue
            if max(start, other_start) < min(end, other_end):
                valid[left] = False
                break
    return valid


def _extract_structured_claims(blocks: list[ParsedBlock], language: str) -> list[dict]:
    labelled = "\n".join(
        f"[{block.block_id}|{block.block_type}]\n{block.original_text}"
        for block in blocks if block.block_type != "blank"
    )
    result = llm_client.chat_with_tools(
        messages=[
            {"role": "system", "content": STRUCTURED_CLAIM_EXTRACTION_SYSTEM},
            {"role": "user", "content": f"{language_instruction(language)}\n\n{labelled}"},
        ],
        tools=[STRUCTURED_CLAIM_EXTRACTION_TOOL],
        tool_choice={"type": "function", "function": {"name": "submit_structured_claims"}},
        temperature=0.0,
    )
    claims = result.get("claims", [])
    output = []
    for index, item in enumerate(claims[:25], start=1):
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim") or "").strip()
        fragment = str(item.get("source_fragment") or "")
        block_id = str(item.get("block_id") or "")
        if claim and fragment and block_id:
            output.append({
                "claim_id": f"C{index}",
                "block_id": block_id,
                "source_fragment": fragment,
                "claim": claim,
            })
    return output


def _propose_repair(claim: Claim, language: str) -> dict:
    evidence = "\n\n".join(
        f"[{item.evidence_id}] {item.title}\n{item.excerpt}" for item in claim.evidence
    )
    result = llm_client.chat_with_tools(
        messages=[
            {"role": "system", "content": REPAIR_CLAIM_SYSTEM},
            {"role": "user", "content": (
                f"{language_instruction(language)}\n\n"
                f"Original claim: {claim.claim}\nFirst verdict: {claim.verdict}\n\n"
                f"Selected evidence:\n{evidence}"
            )},
        ],
        tools=[REPAIR_CLAIM_TOOL],
        tool_choice={"type": "function", "function": {"name": "submit_claim_repair"}},
        temperature=0.0,
    )
    return result


def _locate_across_blocks(
    content_blocks: list[ParsedBlock], fragment: str, claim: str
) -> tuple[ParsedBlock | None, tuple[int, int] | None]:
    """Find a fragment/claim anywhere, recovering from a renumbered ``block_id``.

    Used only as a last resort: accepts a hit when exactly one block matches.
    """
    hits: list[tuple[ParsedBlock, tuple[int, int]]] = []
    for candidate in content_blocks:
        span = locate_source_fragment(candidate, fragment)
        if span is None and claim:
            span = locate_source_fragment(candidate, claim)
        if span:
            hits.append((candidate, span))
    return hits[0] if len(hits) == 1 else (None, None)


def _drop_span(row: dict) -> None:
    row["block_start"] = row["block_end"] = None
    row.pop("source_start", None)
    row.pop("source_end", None)


def _resolve_overlaps(mapped: list[dict], entries: list[tuple[int, int, int]]) -> None:
    """Keep the earliest / longest span in a block; null the ones it overlaps."""
    kept: list[tuple[int, int]] = []
    for row_index, start, end in sorted(entries, key=lambda e: (e[1], -(e[2] - e[1]))):
        if any(max(start, ks) < min(end, ke) for ks, ke in kept):
            _drop_span(mapped[row_index])
        else:
            kept.append((start, end))


def _map_extracted_claims(extracted: list[dict], blocks: list[ParsedBlock]) -> list[dict]:
    by_id = {block.block_id: block for block in blocks}
    content_blocks = [block for block in blocks if block.block_type != "blank"]
    mapped: list[dict] = []
    spans_by_block: dict[str, list[tuple[int, int, int]]] = {}
    for item in extracted:
        row = dict(item)
        fragment = str(row.get("source_fragment") or "")
        claim = str(row.get("claim") or "")
        block = by_id.get(str(row.get("block_id")))
        span = locate_source_fragment(block, fragment)
        if span is None and block is not None and claim:
            span = locate_source_fragment(block, claim)
        if span is None:
            block, span = _locate_across_blocks(content_blocks, fragment, claim)
        if span and block is not None:
            row["block_id"] = block.block_id
            row["block_start"], row["block_end"] = span
            row["source_start"] = block.source_offset + span[0]
            row["source_end"] = block.source_offset + span[1]
            spans_by_block.setdefault(block.block_id, []).append((len(mapped), *span))
        else:
            _drop_span(row)
        mapped.append(row)
    for entries in spans_by_block.values():
        _resolve_overlaps(mapped, entries)
    return mapped


def _make_record(claim: Claim, mapped: dict, index: int) -> RepairRecord:
    valid_span = mapped.get("block_start") is not None
    if claim.verdict == "correct" and claim.evidence_status == "cited":
        status, reason = "not_needed", None
    elif not valid_span:
        status, reason = "unresolved", "invalid_span"
    elif claim.verdict == "insufficient_evidence":
        status, reason = "unresolved", "insufficient_evidence"
    elif claim.verdict == "verification_failed":
        status, reason = "failed", "service_failure"
    else:
        status, reason = "unresolved", None
    return RepairRecord(
        repair_id=f"R{index}",
        claim_id=str(claim.claim_id or mapped.get("claim_id") or f"C{index}"),
        block_id=str(claim.source_block_id or mapped.get("block_id") or ""),
        source_fragment=str(mapped.get("source_fragment") or claim.claim),
        block_start=mapped.get("block_start"),
        block_end=mapped.get("block_end"),
        original_claim=claim.claim,
        repair_status=status,
        unresolved_reason=reason,
        first_verdict=claim.verdict,
        confidence=claim.confidence,
    )


def _apply_records(blocks: list[ParsedBlock], records: list[RepairRecord]) -> list[NoteBlock]:
    records_by_block: dict[str, list[RepairRecord]] = {}
    for record in records:
        records_by_block.setdefault(record.block_id, []).append(record)
    output: list[NoteBlock] = []
    for block in blocks:
        related = records_by_block.get(block.block_id, [])
        text = block.original_text
        # Splice in verified repairs only. Unresolved / failed claims (mapped or
        # not) are left exactly as written — the note keeps every original
        # sentence; the claim is still surfaced in the revision history.
        replacements = [
            (record.block_start, record.block_end, record.proposed_claim or "")
            for record in related
            if record.repair_status == "repaired"
            and record.block_start is not None
            and record.block_end is not None
        ]
        for start, end, replacement in sorted(replacements, reverse=True):
            text = text[:start] + replacement + text[end:]
        content_without_marker = text[len(block.marker):].strip() if block.marker else text.strip()
        final_text = text if content_without_marker or block.block_type in {"heading", "blank"} else None
        if final_text is None:
            status = "excluded"
        elif replacements:
            status = "repaired"
        else:
            status = "unchanged"
        output.append(NoteBlock(
            block_id=block.block_id,
            block_type=block.block_type,
            original_text=block.original_text,
            final_text=final_text,
            marker=block.marker,
            status=status,
            repair_ids=[record.repair_id for record in related],
        ))
    return output


def _repair_one_claim(
    index: int, claim: Claim, mapped: dict, language: str, store: VectorStore
) -> RepairRecord:
    record = _make_record(claim, mapped, index)
    if not (
        claim.verdict in {"incorrect", "incomplete"}
        and claim.evidence_status == "cited"
        and record.block_start is not None
    ):
        return record
    try:
        proposal = _propose_repair(claim, language)
        proposed = str(proposal.get("proposed_claim") or "").strip()
        selected_ids = proposal.get("evidence_ids")
        available_ids = {item.evidence_id for item in claim.evidence}
        selected = {
            str(value) for value in selected_ids if isinstance(value, str)
        } if isinstance(selected_ids, list) else set()
        valid = (
            proposed
            and proposed.casefold() != claim.claim.strip().casefold()
            and bool(selected)
            and selected.issubset(available_ids)
        )
        if not valid:
            record.unresolved_reason = "invalid_proposal"
        else:
            second_response = verify_claims([{
                "claim_id": f"{record.claim_id}-R1",
                "block_id": record.block_id,
                "claim": proposed,
            }], store, language)
            second = second_response.claims[0] if second_response.claims else None
            record.proposed_claim = proposed
            record.change_reason = str(proposal.get("change_reason") or "").strip() or None
            record.second_verdict = second.verdict if second else "verification_failed"
            if second and second.verdict == "correct" and second.evidence_status == "cited":
                record.repair_status = "repaired"
                record.unresolved_reason = None
                record.evidence = second.evidence
                record.confidence = second.confidence
                record.included_by_default = True
            else:
                record.unresolved_reason = "second_verdict_not_correct"
    except Exception as exc:
        logger.warning("Repair failed for claim %r: %s", claim.claim, exc)
        record.repair_status = "failed"
        record.unresolved_reason = "service_failure"
    return record


def run(
    text: str,
    language: str,
    store: VectorStore,
    *,
    preserve_structure: bool = True,
) -> RepairNoteResponse:
    blocks = parse_note_blocks(text)
    extracted = _map_extracted_claims(_extract_structured_claims(blocks, language), blocks)
    verification = verify_claims(extracted, store, language)
    mapped_by_id = {str(item.get("claim_id")): item for item in extracted}

    indexed = list(enumerate(verification.claims, start=1))
    records = run_concurrent(
        indexed,
        worker=lambda pair: _repair_one_claim(
            pair[0], pair[1], mapped_by_id.get(str(pair[1].claim_id), {}), language, store
        ),
        on_error=lambda pair, exc: _make_record(
            pair[1], mapped_by_id.get(str(pair[1].claim_id), {}), pair[0]
        ),
    )

    public_blocks = _apply_records(blocks, records)
    if preserve_structure:
        repaired_note = "".join(block.final_text or "" for block in public_blocks)
        if not repaired_note.strip():
            repaired_note = text
    else:
        repaired_note = "\n".join(
            record.proposed_claim if record.repair_status == "repaired" else record.original_claim
            for record in records if record.repair_status in {"repaired", "not_needed"}
        )
    unresolved_ids = {
        record.claim_id for record in records if record.repair_status in {"unresolved", "failed"}
    }
    unresolved = [claim for claim in verification.claims if str(claim.claim_id) in unresolved_ids]
    tags: list[str] = []
    if repaired_note.strip():
        try:
            tags = _extract_tags(repaired_note)
        except Exception:
            logger.warning("Tag extraction failed for repaired note", exc_info=True)
    return RepairNoteResponse(
        original_text=text,
        verification=verification,
        repaired_note=repaired_note,
        blocks=public_blocks,
        repairs=records,
        unresolved_claims=unresolved,
        tags=tags,
    )
