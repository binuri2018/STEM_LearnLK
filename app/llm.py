"""LLM answer with strict syllabus-only system prompt; English / Sinhala / auto response."""
from __future__ import annotations

import httpx
from openai import OpenAI

from app.config import settings

BASE_SYSTEM = (
    "You are a helpful Sri Lankan OL science tutor. Answer the student's question clearly and accurately "
    "using the provided syllabus context.\n"
    "- Combine definitions, formulas, and facts present across the context chunks to answer comparisons and conceptual questions.\n"
    "- Do not invent outside facts.\n"
    "- If and only if the topic is completely absent and cannot be answered from the context, use the required refusal phrase."
)

REFUSAL_EN = "This is not in the syllabus."
REFUSAL_SI = "මෙය විෂය මාලාවේ හෝ ලබා දී ඇති සම්පත්වල අන්තර්ගත නොවේ."

LANG_RULES = {
    "en": (
        f"If the context truly does not contain the information, reply with exactly: {REFUSAL_EN!r}\n"
        "Otherwise, write a clear, helpful answer in English based on the context."
    ),
    "si": (
        f"If the context truly does not contain the information, reply with exactly: {REFUSAL_SI}\n"
        "Otherwise, write a clear, helpful answer in Sinhala (සිංහල අකුරු භාවිතා කරන්න) based on the context."
    ),
    "auto": (
        f"If the context truly does not contain the information, reply in the student's language: "
        f"use {REFUSAL_EN!r} for English questions and {REFUSAL_SI} for Sinhala questions.\n"
        "Otherwise, answer in the same language as the student question (English or Sinhala) using the context."
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
