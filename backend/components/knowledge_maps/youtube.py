"""YouTube analysis pipeline (Step 5).

Fetches a video transcript, cleans it, then runs verification + three
synthesis modes (notes, flashcards, mindmap) in sequence.

Public API:
  analyze_video(url, language, store) -> YoutubeResponse
"""
from __future__ import annotations

import re

from backend.components.knowledge_maps import llm_client
from backend.components.knowledge_maps.prompts import (
    VIDEO_SUMMARY_SYSTEM,
    VIDEO_SUMMARY_TOOL,
    YOUTUBE_CLEAN_SYSTEM,
    youtube_clean_user,
)
from backend.components.knowledge_maps.schemas import Flashcard, YoutubeResponse
from backend.components.knowledge_maps.synthesis import synthesize
from backend.components.knowledge_maps.verification import verify_text
from backend.common.vector_store import VectorStore

# Transcript is capped so local and cloud calls stay predictable.
_TRANSCRIPT_CHAR_LIMIT = 6000
# Excerpt shown in the UI transcript preview panel.
_EXCERPT_CHAR_LIMIT = 800


# ─── Video ID extraction ───────────────────────────────────────────────────

_YT_PATTERNS = [
    r"(?:v=)([A-Za-z0-9_-]{11})",          # ?v=xxxx or &v=xxxx
    r"youtu\.be/([A-Za-z0-9_-]{11})",       # youtu.be/xxxx
    r"shorts/([A-Za-z0-9_-]{11})",          # youtube.com/shorts/xxxx
    r"embed/([A-Za-z0-9_-]{11})",           # youtube.com/embed/xxxx
]


def _extract_video_id(url: str) -> str:
    for pattern in _YT_PATTERNS:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    raise ValueError(
        f"Cannot extract a YouTube video ID from URL: {url!r}. "
        "Supported formats: youtube.com/watch?v=..., youtu.be/..., "
        "youtube.com/shorts/..."
    )


# ─── Transcript fetch ──────────────────────────────────────────────────────

def _entry_text(e) -> str:
    """Extract text from a transcript entry regardless of API version.

    youtube-transcript-api <0.7 returns plain dicts; >=0.7 returns
    FetchedTranscriptSnippet objects with a .text attribute.
    """
    return e["text"] if isinstance(e, dict) else getattr(e, "text", "")


def _fetch_transcript(video_id: str, language: str) -> str:
    """Return raw transcript text, capped at _TRANSCRIPT_CHAR_LIMIT chars.

    Compatible with youtube-transcript-api 1.x (instance-based API).
    """
    try:
        from youtube_transcript_api import (  # optional dep — lazy import
            CouldNotRetrieveTranscript,
            NoTranscriptFound,
            TranscriptsDisabled,
            VideoUnavailable,
            YouTubeTranscriptApi,
        )
    except ImportError as exc:
        raise RuntimeError(
            "youtube-transcript-api is not installed. "
            "Run: pip install youtube-transcript-api"
        ) from exc

    api = YouTubeTranscriptApi()

    # Try requested language first, then English, then Sinhala
    lang_prefs: list[list[str]] = []
    if language and language != "auto":
        lang_prefs.append([language, "en"])
    lang_prefs.append(["en"])
    lang_prefs.append(["si"])

    _transient = (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable, CouldNotRetrieveTranscript)

    last_exc: Exception | None = None
    for langs in lang_prefs:
        try:
            fetched = api.fetch(video_id, languages=langs)
            text = " ".join(_entry_text(e) for e in fetched if _entry_text(e))
            return text[:_TRANSCRIPT_CHAR_LIMIT]
        except _transient as exc:
            last_exc = exc
            continue
        except Exception as exc:
            last_exc = exc
            break

    # Last resort: pick any auto-generated transcript available
    try:
        transcript_list = api.list(video_id)
        transcript = transcript_list.find_generated_transcript(["en", "si"])
        fetched = transcript.fetch()
        text = " ".join(_entry_text(e) for e in fetched if _entry_text(e))
        return text[:_TRANSCRIPT_CHAR_LIMIT]
    except Exception:
        pass

    error_name = type(last_exc).__name__ if last_exc else "Unknown"
    raise ValueError(
        f"Could not fetch transcript for video {video_id!r} "
        f"({error_name}). The video may have captions disabled or be unavailable."
    )


# ─── Transcript cleaning ───────────────────────────────────────────────────

def _clean_transcript(raw: str) -> str:
    """Use the selected LLM to clean broken auto-generated transcript text."""
    try:
        result = llm_client.chat_json(
            YOUTUBE_CLEAN_SYSTEM,
            youtube_clean_user(raw),
            temperature=0.1,
        )
        # chat_json returns dict — extract first string value
        if isinstance(result, dict):
            cleaned = next(
                (str(v) for v in result.values() if isinstance(v, str) and v.strip()),
                ""
            )
        else:
            cleaned = str(result)
        return cleaned.strip() or raw  # fall back to raw if cleaning fails
    except Exception:
        return raw  # cleaning is best-effort — never block the pipeline


# ─── Lightweight summary ──────────────────────────────────────────────────

def summarize_video(url: str, language: str) -> dict:
    """Fetch a transcript and return a short note-ready summary.

    Lighter than analyze_video() — no verification or synthesis passes.

    Raises:
      ValueError  — bad URL, captions disabled, video unavailable
      RuntimeError — LLM provider not configured / transcript library missing
    """
    video_id = _extract_video_id(url)
    raw = _fetch_transcript(video_id, language)
    cleaned = _clean_transcript(raw)

    messages = [
        {"role": "system", "content": VIDEO_SUMMARY_SYSTEM},
        {"role": "user", "content": f"Transcript:\n\"\"\"\n{cleaned}\n\"\"\""},
    ]
    result = llm_client.chat_with_tools(
        messages=messages,
        tools=[VIDEO_SUMMARY_TOOL],
        tool_choice={"type": "function", "function": {"name": "submit_video_summary"}},
        temperature=0.3,
    )
    return {
        "summary": result.get("summary", ""),
        "key_points": result.get("key_points", []),
        "title": "",
    }


# ─── Main pipeline ─────────────────────────────────────────────────────────

def analyze_video(
    url: str,
    language: str,
    store: VectorStore,
) -> YoutubeResponse:
    """Full YouTube analysis: transcript → clean → verify + 3x synthesize.

    Raises:
      ValueError  — bad URL, captions disabled, video unavailable
      RuntimeError — LLM provider not configured / transcript library missing
    """
    video_id = _extract_video_id(url)
    raw_transcript = _fetch_transcript(video_id, language)
    cleaned = _clean_transcript(raw_transcript)

    # Transcript excerpt shown in the UI preview panel
    excerpt = cleaned[:_EXCERPT_CHAR_LIMIT]
    if len(cleaned) > _EXCERPT_CHAR_LIMIT:
        excerpt += "…"

    # Run verification and all three synthesis modes sequentially.
    # Sequential execution avoids saturating a local model and keeps cloud
    # fallback rate limits predictable.
    verification = verify_text(cleaned, store, language)
    notes_result = synthesize(cleaned, "notes", language)
    flashcards_result = synthesize(cleaned, "flashcards", language)
    mindmap_result = synthesize(cleaned, "mindmap", language)

    # synthesize() returns raw dicts — extract the flashcard list for
    # the typed field, keep notes and mindmap as dicts (frontend expects that)
    raw_flashcards = flashcards_result.get("flashcards", [])
    flashcards = [
        Flashcard(front=fc.get("front", ""), back=fc.get("back", ""))
        for fc in raw_flashcards
        if isinstance(fc, dict)
    ]

    return YoutubeResponse(
        transcript_excerpt=excerpt,
        verification=verification,
        notes=notes_result,
        flashcards=flashcards,
        mind_map=mindmap_result,
    )
