"""LLM answer with strict syllabus-only system prompt; English / Sinhala / auto response."""
from __future__ import annotations

import httpx
from openai import OpenAI

from app.config import settings

BASE_SYSTEM = (
    "Answer ONLY using the provided context. If the answer is not found, do not invent facts. "
    "When you must refuse, use the exact refusal phrase required by the response-language rule below."
)

REFUSAL_EN = "This is not in the syllabus."
REFUSAL_SI = "මෙය විෂය මාලාවේ හෝ ලබා දී ඇති සම්පත්වල අන්තර්ගත නොවේ."

LANG_RULES = {
    "en": (
        f"If (and only if) the context does not contain the answer, reply with exactly: {REFUSAL_EN!r}\n"
        "Otherwise write the full answer in clear English."
    ),
    "si": (
        f"If (and only if) the context does not contain the answer, reply with exactly: {REFUSAL_SI}\n"
        "Otherwise write the full answer in clear Sinhala (සිංහල අකුරු භාවිතා කරන්න)."
    ),
    "auto": (
        f"If (and only if) the context does not contain the answer, reply in the same language as the "
        f"question: use {REFUSAL_EN!r} for English-style questions and {REFUSAL_SI} for Sinhala-style questions.\n"
        "Otherwise answer in the same language as the student question (English and/or Sinhala as appropriate)."
    ),
}


def answer_question(
    context: str,
    question: str,
    response_language: str = "auto",
) -> str:
    lang = (response_language or "auto").lower()
    if lang not in LANG_RULES:
        lang = "auto"
    system_content = BASE_SYSTEM + "\n\n" + LANG_RULES[lang]
    if settings.openai_api_key and settings.openai_api_key.strip():
        return _openai_answer(system_content, context, question)
    return _ollama_answer(system_content, context, question)


def _openai_answer(system_content: str, context: str, question: str) -> str:
    client = OpenAI(api_key=settings.openai_api_key)
    user_content = f"""Context from syllabus materials:\n\n{context}\n\nStudent question:\n{question}"""
    r = client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
    )
    if not r.choices or not r.choices[0].message.content:
        return REFUSAL_EN
    return r.choices[0].message.content.strip()


def _ollama_answer(system_content: str, context: str, question: str) -> str:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    user_content = f"""Context from syllabus materials:\n\n{context}\n\nStudent question:\n{question}"""
    payload = {
        "model": settings.ollama_chat_model,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    with httpx.Client(timeout=settings.ollama_timeout_seconds) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
    msg = data.get("message", {}) or {}
    content = (msg.get("content") or "").strip()
    return content or REFUSAL_EN
