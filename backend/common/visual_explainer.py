"""
Context-Aware Internet Image Retrieval & Visual Explanation Module.

Analyzes student questions, determines if a visual explanation is needed,
generates educational search queries, retrieves candidate images from trusted online
sources (Wikipedia & Wikimedia Commons), scores relevance, and selects high-confidence
diagrams (threshold >= 0.80) with full source attribution.
"""
from __future__ import annotations

import datetime
import json
import logging
import re
from pathlib import Path
from typing import Any, TypedDict

import httpx
import numpy as np

from backend.common.config import settings
from backend.common.embeddings import embed_query

logger = logging.getLogger("backend.visual_explainer")
logger.setLevel(logging.INFO)

# Strict confidence threshold: only show visual if confidence >= 80%
MIN_VISUAL_CONFIDENCE = 0.80

# Visual need indicator keywords (processes, anatomy, structures, cycles, comparisons)
_VISUAL_TOPICS = {
    "human digestive system": ("Human Digestive System", "human digestive system labeled diagram"),
    "digestive system": ("Human Digestive System", "human digestive system labeled diagram"),
    "digestive": ("Human Digestive System", "human digestive system labeled diagram"),
    "human respiratory system": ("Human Respiratory System", "human respiratory system diagram"),
    "respiratory system": ("Human Respiratory System", "human respiratory system diagram"),
    "respiratory": ("Human Respiratory System", "human respiratory system diagram"),
    "human circulatory system": ("Circulatory System", "human circulatory system heart diagram"),
    "circulatory system": ("Circulatory System", "human circulatory system heart diagram"),
    "circulatory": ("Circulatory System", "human circulatory system heart diagram"),
    "human excretory system": ("Excretory System", "human excretory system kidney diagram"),
    "excretory system": ("Excretory System", "human excretory system kidney diagram"),
    "excretory": ("Excretory System", "human excretory system kidney diagram"),
    "human nervous system": ("Nervous System", "human nervous system diagram"),
    "nervous system": ("Nervous System", "human nervous system diagram"),
    "photosynthesis": ("Photosynthesis", "photosynthesis process educational diagram"),
    "mitosis": ("Mitosis", "mitosis stages cell division diagram"),
    "meiosis": ("Meiosis", "meiosis stages cell division diagram"),
    "human heart": ("Human Heart", "human heart internal structure labeled diagram"),
    "heart": ("Human Heart", "human heart internal structure labeled diagram"),
    "human brain": ("Human Brain", "human brain structure labeled diagram"),
    "brain": ("Human Brain", "human brain structure labeled diagram"),
    "plant cell": ("Plant Cell", "plant cell structure labeled diagram"),
    "animal cell": ("Animal Cell", "animal cell structure labeled diagram"),
    "cell structure": ("Cell (biology)", "labeled cell structure diagram"),
    "chloroplast": ("Chloroplast", "chloroplast internal structure diagram"),
    "mitochondria": ("Mitochondrion", "mitochondria structure diagram"),
    "flower": ("Flower", "flower reproductive parts labeled diagram"),
    "nephron": ("Nephron", "nephron structure kidney diagram"),
    "neuron": ("Neuron", "neuron structure labeled diagram"),
    "reflex arc": ("Reflex Arc", "reflex arc pathway diagram"),
    "electric circuit": ("Electrical Circuit", "electric circuit schematic diagram"),
    "circuit": ("Electrical Circuit", "electric circuit schematic diagram"),
    "ohm": ("Ohm's Law", "ohms law circuit triangle diagram"),
    "refraction": ("Refraction", "light refraction ray diagram"),
    "reflection": ("Reflection", "light reflection mirror ray diagram"),
    "lens": ("Lens", "convex concave lens ray diagram"),
    "dispersion": ("Dispersion (optics)", "prism light dispersion spectrum diagram"),
    "wave": ("Wave", "transverse longitudinal wave diagram"),
    "periodic table": ("Periodic Table", "periodic table of elements"),
    "atomic structure": ("Atom", "atomic structure subatomic particles diagram"),
    "atom": ("Atom", "atomic structure subatomic particles diagram"),
    "water cycle": ("Water Cycle", "water cycle hydrologic diagram"),
    "carbon cycle": ("Carbon Cycle", "carbon cycle process diagram"),
    "nitrogen cycle": ("Nitrogen Cycle", "nitrogen cycle process diagram"),
    "electrolysis": ("Electrolysis", "electrolysis apparatus cathode anode diagram"),
    "dna": ("DNA", "dna double helix structure diagram"),
    "chromosome": ("Chromosome", "chromosome structure chromatid centromere diagram"),
}

# Non-visual patterns: greetings, simple arithmetic, pure definitions, dates
_NON_VISUAL_PATTERNS = [
    r"^\s*(hi|hello|hey|good\s+(morning|afternoon|evening)|how\s+are\s+you|thank\s+you|thanks)\b",
    r"^\s*what\s+is\s+\d+\s*[\+\-\*\/×÷]\s*\d+",
    r"^\s*\d+\s*[\+\-\*\/×÷]\s*\d+",
    r"^\s*(who\s+wrote|when\s+was|what\s+year|who\s+is\s+the\s+president)\b",
]


class VisualMetadata(TypedDict):
    image_url: str
    title: str
    source_name: str
    source_url: str
    search_query: str
    relevance_score: float


def analyze_visual_need(question: str) -> tuple[bool, str, str]:
    """
    Determine whether a student's question benefits from a visual explanation.
    Returns: (needs_visual, extracted_concept, optimized_search_query)
    """
    q_clean = question.strip()
    q_low = q_clean.lower()

    # 1. Reject non-visual patterns (greetings, math arithmetic, dates)
    for pat in _NON_VISUAL_PATTERNS:
        if re.search(pat, q_low, re.I):
            return False, "", ""

    # 2. Check for specific visual topics (longest / most specific first)
    for topic_kw in sorted(_VISUAL_TOPICS.keys(), key=len, reverse=True):
        if re.search(r"\b" + re.escape(topic_kw) + r"\b", q_low):
            concept, suggested_query = _VISUAL_TOPICS[topic_kw]
            return True, concept, suggested_query

    # 3. Check for general visual keywords ("how does X work", "explain X", "diagram of X", "structure of X")
    visual_triggers = [
        (r"(?:structure|anatomy|diagram|parts|cross\s*section|model)\s+of\s+(?:the\s+)?([a-zA-Z\s]{3,30})", "structure labeled diagram"),
        (r"(?:explain|describe|how\s+does)\s+(?:the\s+)?([a-zA-Z\s]{3,30})(?:\s+work|\s+occur|\s+function)?", "process educational diagram"),
        (r"compare\s+([a-zA-Z\s]{3,20})\s+and\s+([a-zA-Z\s]{3,20})", "comparison diagram"),
        (r"difference\s+between\s+([a-zA-Z\s]{3,20})\s+and\s+([a-zA-Z\s]{3,20})", "comparison diagram"),
    ]

    for pat, suffix in visual_triggers:
        m = re.search(pat, q_low, re.I)
        if m:
            groups = [g.strip() for g in m.groups() if g]
            concept = " vs ".join(groups).title()
            query = f"{' '.join(groups)} {suffix}".strip()
            return True, concept, query

    # Default to False for general questions
    return False, "", ""


def retrieve_trusted_online_images(query: str, concept: str = "", max_candidates: int = 6) -> list[dict]:
    """
    Fetch candidate images from trusted educational internet sources (Wikipedia REST & Wikimedia Commons).
    """
    candidates: list[dict] = []
    seen_urls: set[str] = set()

    headers = {
        "User-Agent": "STEMLearnLK-ScienceTutor/1.0 (https://stemlearnlk.org; educational AI tutor)",
        "Accept": "application/json",
    }

    # 1. Direct Wikipedia REST Summary lookup for the primary concept (super fast, <300ms)
    direct_titles = []
    if concept:
        direct_titles.append(concept.replace(" ", "_"))
        sentence_cased = (concept[0].upper() + concept[1:].lower()).replace(" ", "_")
        if sentence_cased not in direct_titles:
            direct_titles.append(sentence_cased)
        if "digestive" in concept.lower() and "human" not in concept.lower():
            direct_titles.append("Human_digestive_system")
        elif "cell" in concept.lower() and "plant" not in concept.lower() and "animal" not in concept.lower():
            direct_titles.append("Cell_(biology)")
        elif "plant cell" in concept.lower():
            direct_titles.append("Plant_cell")
        elif "animal cell" in concept.lower():
            direct_titles.append("Animal_cell")

    for dtitle in direct_titles:
        rest_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{dtitle}"
        try:
            with httpx.Client(headers=headers, timeout=4.0, verify=False) as client:
                r = client.get(rest_url)
                if r.status_code == 200:
                    data = r.json()
                    thumb = data.get("thumbnail", {}).get("source") or data.get("originalimage", {}).get("source")
                    if thumb and thumb not in seen_urls:
                        seen_urls.add(thumb)
                        title = data.get("title", "")
                        desc = data.get("description", "") or data.get("extract", "")
                        source_url = data.get("content_urls", {}).get("desktop", {}).get("page", f"https://en.wikipedia.org/wiki/{dtitle}")
                        candidates.append({
                            "title": title,
                            "image_url": thumb,
                            "source_url": source_url,
                            "source_name": "Wikipedia",
                            "description": f"{title}. {desc}".strip()[:350],
                        })
        except Exception as exc:
            logger.debug("[visual_explainer] REST summary failed for %s: %s", dtitle, exc)

    # 2. Wikipedia Action API search for diagram articles
    search_term = f"{concept} diagram" if concept else query
    wiki_url = "https://en.wikipedia.org/w/api.php"
    params_wiki = {
        "action": "query",
        "generator": "search",
        "gsrsearch": search_term,
        "gsrlimit": str(max_candidates),
        "prop": "pageimages|description|pageterms",
        "piprop": "original|thumbnail",
        "pithumbsize": "800",
        "format": "json",
    }
    try:
        with httpx.Client(headers=headers, timeout=5.0, verify=False) as client:
            r = client.get(wiki_url, params=params_wiki)
            if r.status_code == 200:
                data = r.json()
                pages = data.get("query", {}).get("pages", {})
                for pid, p in pages.items():
                    thumb = p.get("thumbnail", {}).get("source") or p.get("original", {}).get("source")
                    if not thumb or thumb in seen_urls:
                        continue
                    seen_urls.add(thumb)
                    title = p.get("title", "")
                    desc = p.get("description", "")
                    terms = p.get("terms", {}).get("description", [])
                    term_desc = terms[0] if terms else ""
                    clean_title = title.replace("_", " ")
                    candidates.append({
                        "title": clean_title,
                        "image_url": thumb,
                        "source_url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                        "source_name": "Wikipedia",
                        "description": f"{clean_title}. {desc}. {term_desc}".strip()[:350],
                    })
    except Exception as exc:
        logger.debug("[visual_explainer] Wikipedia search query failed: %s", exc)

    # 3. Wikimedia Commons file search for labeled diagrams
    if len(candidates) < 4:
        commons_url = "https://commons.wikimedia.org/w/api.php"
        commons_term = f"{concept} labeled diagram" if concept else query
        params_commons = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"{commons_term} filetype:bitmap|drawing",
            "gsrnamespace": "6",
            "gsrlimit": str(max_candidates),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiurlwidth": "800",
            "format": "json",
        }
        try:
            with httpx.Client(headers=headers, timeout=5.0, verify=False) as client:
                r = client.get(commons_url, params=params_commons)
                if r.status_code == 200:
                    data = r.json()
                    pages = data.get("query", {}).get("pages", {})
                    for pid, p in pages.items():
                        raw_title = p.get("title", "")
                        title = re.sub(r"^File:", "", raw_title)
                        title = re.sub(r"\.(svg|png|jpg|jpeg|webp)$", "", title, flags=re.I)
                        title = title.replace("_", " ").replace("-", " ")
                        infos = p.get("imageinfo", [])
                        if not infos:
                            continue
                        info = infos[0]
                        thumb = info.get("thumburl") or info.get("url")
                        if not thumb or thumb in seen_urls:
                            continue
                        seen_urls.add(thumb)
                        meta = info.get("extmetadata", {})
                        raw_desc = meta.get("ImageDescription", {}).get("value", "")
                        clean_desc = re.sub(r"<[^>]+>", " ", raw_desc).strip()
                        desc = " ".join(clean_desc.split())[:300]
                        candidates.append({
                            "title": title.strip(),
                            "image_url": thumb,
                            "source_url": info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{raw_title}",
                            "source_name": "Wikimedia Commons",
                            "description": desc or title,
                        })
        except Exception as exc:
            logger.debug("[visual_explainer] Wikimedia Commons query failed: %s", exc)

    return candidates


def score_and_select_visual(
    question: str,
    concept: str,
    search_query: str,
    candidates: list[dict],
) -> tuple[VisualMetadata | None, float]:
    """
    Score candidates using semantic similarity and keyword alignment.
    Returns: (best_visual_metadata_or_none, best_score)
    """
    if not candidates:
        return None, 0.0

    # 1. Embed student question and concept
    q_text = f"{question} {concept}".strip()
    q_vec = embed_query(q_text)
    if isinstance(q_vec, np.ndarray) and q_vec.ndim == 2:
        q_vec = q_vec[0]

    # Normalize q_vec
    q_norm = np.linalg.norm(q_vec)
    if q_norm > 0:
        q_vec = q_vec / q_norm

    best_candidate: dict | None = None
    best_score = 0.0

    # Extract key informative words (ignoring common conversational stop words)
    _STOPWORDS = {"what", "is", "the", "how", "does", "explain", "describe", "compare", "between", "and", "or", "of", "in", "to", "a", "an", "are", "with", "tell", "about"}
    q_words = {w.lower() for w in re.findall(r"[a-zA-Z]{3,}", f"{question} {concept}") if w.lower() not in _STOPWORDS}
    concept_lower = concept.lower().strip()

    for cand in candidates:
        title = cand.get("title", "")
        desc = cand.get("description", "")
        combined_text = f"{title}. {desc}".strip()
        title_lower = title.lower()

        # Embed candidate description
        c_vec = embed_query(combined_text)
        if isinstance(c_vec, np.ndarray) and c_vec.ndim == 2:
            c_vec = c_vec[0]
        c_norm = np.linalg.norm(c_vec)
        if c_norm > 0:
            c_vec = c_vec / c_norm

        # Cosine similarity
        cosine_sim = float(np.dot(q_vec, c_vec))
        norm_sim = max(0.0, min(1.0, cosine_sim))

        # Keyword alignment
        cand_words = {w.lower() for w in re.findall(r"[a-zA-Z]{3,}", combined_text)}
        overlap_cnt = len(q_words.intersection(cand_words))
        kw_ratio = overlap_cnt / max(1, len(q_words))

        # Base composite score
        composite = (norm_sim * 0.55) + (kw_ratio * 0.35)

        # Concept title match bonus: candidate directly represents the requested concept
        if concept_lower and (concept_lower in title_lower or title_lower in concept_lower):
            composite += 0.16
        elif any(w in title_lower for w in q_words if len(w) >= 4):
            composite += 0.08

        # Educational diagram / structure bonus
        if any(term in title_lower or term in desc.lower() for term in ["diagram", "structure", "system", "cycle", "process", "model", "illustration", "labeled", "cell", "anatomy"]):
            composite += 0.08

        # Normalize score into clean 0.0 - 0.99 range
        relevance_score = round(min(0.98, max(0.0, composite)), 2)

        logger.info(
            "  [VISUAL CANDIDATE] Title='%s' | Sim=%.3f | KwRatio=%.2f | Score=%.2f",
            title[:40], norm_sim, kw_ratio, relevance_score
        )

        if relevance_score > best_score:
            best_score = relevance_score
            best_candidate = cand

    # Threshold evaluation (>= 80%)
    if best_score >= MIN_VISUAL_CONFIDENCE and best_candidate:
        visual_meta: VisualMetadata = {
            "image_url": best_candidate["image_url"],
            "title": best_candidate["title"],
            "source_name": best_candidate.get("source_name", "Educational Source"),
            "source_url": best_candidate.get("source_url", ""),
            "search_query": search_query,
            "relevance_score": best_score,
        }
        return visual_meta, best_score

    return None, best_score


def log_visual_retrieval_event(
    question: str,
    concept: str,
    visual_required: bool,
    search_query: str,
    selected_visual: VisualMetadata | None,
    relevance_score: float,
    user_id: str = "student_default",
) -> None:
    """Log visual explanation events for future audit and personalization."""
    log_dir = settings.resolved_data_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "visual_retrieval_logs.jsonl"

    record = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "user_id": user_id,
        "question": question,
        "extracted_concept": concept,
        "visual_required": visual_required,
        "search_query": search_query,
        "relevance_score": relevance_score,
        "selected_visual": selected_visual,
    }

    try:
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("[visual_explainer] Failed to log visual event: %s", exc)


def retrieve_visual_explanation(question: str) -> tuple[bool, VisualMetadata | None]:
    """
    Main entry point for Dynamic Visual Explanation Retrieval.
    Returns: (visual_required, visual_object_or_None)
    """
    q = question.strip()
    if not q:
        return False, None

    needs_visual, concept, search_query = analyze_visual_need(q)
    if not needs_visual:
        log_visual_retrieval_event(q, "", False, "", None, 0.0)
        return False, None

    logger.info("[visual_explainer] Visual recommended for: '%s' | Concept='%s' | Query='%s'", q, concept, search_query)

    candidates = retrieve_trusted_online_images(search_query, concept=concept)
    visual_meta, score = score_and_select_visual(q, concept, search_query, candidates)

    if visual_meta:
        logger.info("[visual_explainer] Selected visual: '%s' (Confidence=%.1f%%)", visual_meta["title"], score * 100)
        log_visual_retrieval_event(q, concept, True, search_query, visual_meta, score)
        return True, visual_meta
    else:
        logger.info("[visual_explainer] No candidate met confidence threshold (%.2f < %.2f)", score, MIN_VISUAL_CONFIDENCE)
        log_visual_retrieval_event(q, concept, False, search_query, None, score)
        return False, None
