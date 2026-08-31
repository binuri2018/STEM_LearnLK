"""Strict URL-backed web fallback for claim verification."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlsplit

from backend.common.config import settings
from backend.components.knowledge_maps import llm_client
from backend.components.knowledge_maps.prompts import WEB_JUDGE_SYSTEM, WEB_JUDGE_TOOL
from backend.components.knowledge_maps.schemas import EvidenceItem

logger = logging.getLogger(__name__)

_MAX_RESULTS = 3
_MAX_SNIPPET_CHARS = 600


@dataclass(frozen=True)
class WebSearchResult:
    evidence_id: str
    title: str
    url: str
    domain: str
    snippet: str


@dataclass(frozen=True)
class WebCheckResult:
    verdict: str
    evidence: list[EvidenceItem]

    @property
    def is_correct(self) -> bool:
        return self.verdict == "correct" and bool(self.evidence)


class WebSearchUnavailable(RuntimeError):
    """Raised when the optional web decision could not be completed."""


def _valid_http_url(value: object) -> tuple[str, str] | None:
    raw = str(value or "").strip()
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return raw, parsed.hostname.lower()


def normalise_web_results(raw_results: list[dict]) -> list[WebSearchResult]:
    """Keep complete HTTP(S) search results and assign request-local IDs."""
    valid: list[WebSearchResult] = []
    for raw in raw_results:
        if not isinstance(raw, dict):
            continue
        parsed_url = _valid_http_url(raw.get("href") or raw.get("url"))
        title = str(raw.get("title") or "").strip()
        snippet = str(raw.get("body") or raw.get("snippet") or "").strip()
        if parsed_url is None or not title or not snippet:
            continue
        url, domain = parsed_url
        valid.append(
            WebSearchResult(
                evidence_id=f"W{len(valid) + 1}",
                title=title,
                url=url,
                domain=domain,
                snippet=snippet[:_MAX_SNIPPET_CHARS],
            )
        )
        if len(valid) >= _MAX_RESULTS:
            break
    return valid


def _ddg_results(claim: str, max_results: int = _MAX_RESULTS) -> list[WebSearchResult]:
    try:
        from duckduckgo_search import DDGS
        from duckduckgo_search.exceptions import DuckDuckGoSearchException

        with DDGS(timeout=settings.m4_web_search_timeout_seconds) as ddgs:
            raw = list(ddgs.text(claim, max_results=max_results))
        return normalise_web_results(raw)
    except (ImportError, OSError, RuntimeError, ValueError, DuckDuckGoSearchException) as exc:
        raise WebSearchUnavailable(f"DuckDuckGo search failed: {exc}") from exc


def _judge_results(claim: str, results: list[WebSearchResult]) -> dict:
    blocks = [
        f"[{item.evidence_id}] {item.title}\nURL: {item.url}\nSnippet: {item.snippet}"
        for item in results
    ]
    messages = [
        {"role": "system", "content": WEB_JUDGE_SYSTEM},
        {
            "role": "user",
            "content": f"Claim: {claim}\n\nWeb results:\n\n" + "\n\n".join(blocks),
        },
    ]
    return llm_client.chat_with_tools(
        messages=messages,
        tools=[WEB_JUDGE_TOOL],
        tool_choice={"type": "function", "function": {"name": "submit_web_verdict"}},
        temperature=0.0,
    )


def _domain_allowed(domain: str, allowed_domains: list[str]) -> bool:
    host = domain.strip().lower().rstrip(".")
    return any(host == allowed or host.endswith("." + allowed) for allowed in allowed_domains)


def judge_web_evidence(claim: str, allowed_domains: list[str]) -> WebCheckResult:
    """Return a two-way verdict only from selected results on approved domains."""
    approved = sorted({d.strip().lower().rstrip(".") for d in allowed_domains if d.strip()})
    if not approved:
        return WebCheckResult(verdict="insufficient_evidence", evidence=[])
    results = [r for r in _ddg_results(claim) if _domain_allowed(r.domain, approved)]
    if not results:
        return WebCheckResult(verdict="insufficient_evidence", evidence=[])

    try:
        raw = _judge_results(claim, results)
    except (RuntimeError, ValueError) as exc:
        raise WebSearchUnavailable(f"Web judge failed: {exc}") from exc

    verdict = str(raw.get("verdict") or "").strip().lower()
    if verdict == "insufficient_evidence":
        return WebCheckResult(verdict="insufficient_evidence", evidence=[])
    if verdict not in {"correct", "incorrect"}:
        raise WebSearchUnavailable("Web judge returned an invalid verdict")
    selected_ids = raw.get("evidence_ids")
    if not isinstance(selected_ids, list):
        return WebCheckResult(verdict="insufficient_evidence", evidence=[])
    wanted = {str(value) for value in selected_ids if isinstance(value, str)}

    evidence = [
        EvidenceItem(
            evidence_id=item.evidence_id,
            source_type="web",
            relation="supports" if verdict == "correct" else "refutes",
            title=item.title,
            excerpt=item.snippet,
            url=item.url,
            domain=item.domain,
        )
        for item in results
        if item.evidence_id in wanted
    ]
    if not evidence:
        return WebCheckResult(verdict="insufficient_evidence", evidence=[])
    return WebCheckResult(verdict=verdict, evidence=evidence)


def is_globally_correct(claim: str) -> WebCheckResult:
    """Compatibility wrapper using the configured fail-closed domain policy."""
    from backend.common.config import settings

    allowed = settings.m4_web_allowed_domains.split(",")
    return judge_web_evidence(claim, allowed)
