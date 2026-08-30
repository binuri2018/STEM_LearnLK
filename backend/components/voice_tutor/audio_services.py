"""OpenAI Whisper (speech-to-text) and TTS helpers."""
from __future__ import annotations

from io import BytesIO

from openai import OpenAI

from backend.common.config import settings

_VALID_VOICES = frozenset({"alloy", "echo", "fable", "onyx", "nova", "shimmer"})


def transcribe_bytes(data: bytes, filename: str = "audio.webm") -> str:
    if not settings.openai_api_key or not str(settings.openai_api_key).strip():
        raise RuntimeError("OPENAI_API_KEY is required for Whisper transcription.")
    client = OpenAI(api_key=settings.openai_api_key)
    buf = BytesIO(data)
    buf.name = filename
    result = client.audio.transcriptions.create(model="whisper-1", file=buf)
    return (result.text or "").strip()


def synthesize_speech(text: str, voice: str | None = None) -> bytes:
    if not settings.openai_api_key or not str(settings.openai_api_key).strip():
        raise RuntimeError("OPENAI_API_KEY is required for OpenAI TTS.")
    v = voice or settings.openai_tts_voice
    if v not in _VALID_VOICES:
        v = settings.openai_tts_voice
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.audio.speech.create(
        model=settings.openai_tts_model,
        voice=v,  # type: ignore[arg-type]
        input=text,
        response_format="mp3",
    )
    return response.content
