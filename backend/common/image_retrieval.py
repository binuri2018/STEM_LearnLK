"""
Multi-stage textbook image retrieval with vector search, topic consistency validation,
and strict relevance thresholding.

Stages:
1. Vector Similarity Search on dedicated Image FAISS index using question embedding.
2. Domain / Topic Consistency Check (Physics vs Chemistry vs Biology).
3. Multi-factor Scoring (Semantic similarity + Caption match + Keyword overlap + Chunk alignment).
4. Strict Confidence Thresholding (Precision > Recall: returns [] if uncertain).
5. Comprehensive diagnostic logging.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import faiss  # type: ignore
import numpy as np

from backend.common.config import settings
from backend.common.embeddings import embed_query

logger = logging.getLogger("backend.image_retrieval")
logger.setLevel(logging.INFO)

# Strict thresholds: prioritize precision over recall
MIN_SEMANTIC_SIM = 0.50
MIN_COMPOSITE_SCORE = 0.58
MAX_RETURN_IMAGES = 2

# Domain vocabulary for topic consistency verification
_PHYSICS_TERMS = {
    "speed", "velocity", "acceleration", "motion", "distance", "displacement",
    "force", "newton", "mass", "weight", "gravity", "friction", "inertia",
    "momentum", "work", "energy", "power", "kinetic", "potential", "pressure",
    "density", "current", "voltage", "resistance", "ohm", "circuit", "ammeter",
    "voltmeter", "switch", "cell", "battery", "resistor", "series", "parallel",
    "magnet", "magnetic", "pole", "field", "induction", "electromagnet",
    "wave", "frequency", "wavelength", "amplitude", "reflection", "refraction",
    "mirror", "lens", "focal", "ray", "light", "sound", "heat", "temperature",
    "conduction", "convection", "radiation", "thermal", "expansion", "equilibrium",
}

_BIOLOGY_TERMS = {
    "cell", "nucleus", "cytoplasm", "membrane", "mitochondria", "ribosome",
    "chloroplast", "vacuole", "tissue", "organ", "organelle", "plant", "animal",
    "photosynthesis", "chlorophyll", "stomata", "respiration", "aerobic",
    "anaerobic", "glucose", "leaf", "root", "stem", "xylem", "phloem",
    "deficiency", "chlorosis", "nitrogen", "phosphorus", "potassium", "calcium",
    "magnesium", "iron", "zinc", "nutrient", "growth", "symptom", "disease",
    "microorganism", "bacteria", "fungi", "virus", "algae", "protozoa",
    "digestion", "enzyme", "stomach", "intestine", "heart", "blood", "artery",
    "vein", "capillary", "circulation", "excretion", "kidney", "nephron",
    "neuron", "nerve", "brain", "reflex", "hormone", "endocrine", "reproduction",
    "flower", "pollination", "seed", "germination", "genetics", "gene", "dna",
    "chromosome", "inheritance", "ecosystem", "food chain", "biome", "biodiversity",
}

_CHEMISTRY_TERMS = {
    "atom", "element", "compound", "molecule", "proton", "neutron", "electron",
    "atomic number", "mass number", "isotope", "electronic configuration",
    "periodic table", "group", "period", "metal", "nonmetal", "metalloid",
    "ion", "cation", "anion", "valency", "chemical bond", "covalent", "ionic",
    "chemical formula", "chemical reaction", "reactant", "product", "equation",
    "acid", "base", "salt", "ph", "neutralization", "litmus", "indicator",
    "mole", "molar mass", "concentration", "solubility", "solution", "solvent",
    "solute", "rate of reaction", "catalyst", "exothermic", "endothermic",
    "oxidation", "reduction", "redox", "electrolysis", "cathode", "anode",
    "electrolyte", "metal activity", "corrosion", "rusting", "hydrocarbon",
}

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "what", "which", "who",
    "when", "where", "how", "why", "in", "on", "at", "to", "for", "of",
    "and", "or", "but", "not", "with", "from", "by", "as", "this", "that",
    "it", "its", "i", "you", "we", "they", "he", "she", "explain",
    "describe", "define", "give", "list", "difference", "between",
}


class ImageStore:
    def __init__(self, index: Any, metadatas: list[dict]):
        self.index = index
        self.metadatas = metadatas

    def search(self, query_vec: np.ndarray, k: int = 10) -> list[tuple[float, dict]]:
        if self.index.ntotal == 0:
            return []
        q = query_vec.reshape(1, -1).astype("float32")
        scores, idxs = self.index.search(q, min(k, self.index.ntotal))
        out = []
        for score, i in zip(scores[0], idxs[0], strict=True):
            if i >= 0 and i < len(self.metadatas):
                out.append((float(score), self.metadatas[i]))
        return out


@lru_cache(maxsize=1)
def _load_image_store() -> ImageStore | None:
    data_dir = settings.resolved_data_dir()
    faiss_path = data_dir / settings.image_faiss_index_name
    jsonl_path = data_dir / settings.image_metadata_name
    json_path = data_dir / "image_index.json"

    if not faiss_path.is_file():
        return None

    try:
        index = faiss.read_index(str(faiss_path))
        metadatas: list[dict] = []
        if jsonl_path.is_file():
            with jsonl_path.open(encoding="utf-8") as f:
                for line in f:
                    metadatas.append(json.loads(line))
        elif json_path.is_file():
            with json_path.open(encoding="utf-8") as f:
                metadatas = json.load(f)

        return ImageStore(index=index, metadatas=metadatas)
    except Exception as exc:
        logger.warning("Could not load image store: %s", exc)
        return None


def reload_index() -> None:
    """Clear memory cache after ingest."""
    _load_image_store.cache_clear()


def find_images_for_hits(hits: list[dict], question: str) -> list[dict]:
    """
    Strict multi-stage image retrieval pipeline.
    Returns at most MAX_RETURN_IMAGES confident matches, or [].
    """
    store = _load_image_store()
    if not store:
        logger.info("[image_retrieval] Image vector store not loaded; returning []")
        return []

    q_clean = question.strip()
    if not q_clean:
        return []

    # 1. Embed question and search image vector store
    q_vec = embed_query(q_clean)
    if isinstance(q_vec, np.ndarray) and q_vec.ndim == 2:
        q_vec = q_vec[0]

    raw_candidates = store.search(q_vec, k=10)
    if not raw_candidates:
        logger.info("[image_retrieval] 0 candidates found for query: %s", q_clean)
        return []

    # 2. Extract question keywords & question domain
    q_keywords = _extract_keywords(q_clean)
    q_domain = _detect_domain(q_clean, hits)

    logger.info(
        "[image_retrieval] Query='%s' | Detected Domain=%s | Keywords=%s",
        q_clean, q_domain, list(q_keywords)[:8]
    )

    scored_candidates: list[tuple[float, dict, str]] = []

    for sim_score, meta in raw_candidates:
        image_id = meta.get("image_id", "")
        img_domain = meta.get("subject_area", "Science")
        caption = meta.get("caption", "")
        heading = meta.get("section_heading", "")
        keywords = meta.get("keywords", [])
        nearby = meta.get("nearby_text", "")

        # ── Stage A: Topic / Domain Consistency Check ──────────────────
        if q_domain != "Science" and img_domain != "Science":
            if q_domain != img_domain:
                # Strong domain conflict: e.g. Question=Physics vs Image=Biology
                logger.info(
                    "  [REJECT] %s: Domain mismatch (Q=%s, Img=%s)",
                    image_id, q_domain, img_domain
                )
                continue

        # Check biological vs physical conflicts at keyword level
        if "cell" in q_clean.lower():
            # Biology cell question: reject physics circuit/switch diagrams
            if any(k in f"{caption} {heading} {nearby}".lower() for k in ["circuit", "ammeter", "voltmeter", "velocity", "speed"]):
                continue
        elif any(k in q_clean.lower() for k in ["speed", "velocity", "acceleration", "motion"]):
            # Physics motion question: reject cell/tissue/flower diagrams
            if any(k in f"{caption} {heading} {nearby}".lower() for k in ["cell", "tissue", "nucleus", "chloroplast", "plant deficiency", "chlorosis"]):
                logger.info("  [REJECT] %s: Topic conflict (Biology diagram for motion query)", image_id)
                continue

        # ── Stage B: Multi-Factor Relevance Scoring ────────────────────
        # 1. Semantic Similarity (normalized 0.0 - 1.0)
        norm_semantic = max(0.0, min(1.0, float(sim_score)))

        # 2. Caption Keyword Overlap (0.0 - 1.0)
        cap_overlap = _overlap_ratio(q_keywords, f"{caption} {heading}")

        # 3. Content Keyword Overlap (0.0 - 1.0)
        kw_overlap = _overlap_ratio(q_keywords, " ".join(keywords) + " " + nearby)

        # 4. Text Chunk Provenance Alignment (+0.05 if same page/file as top hit)
        provenance_boost = 0.0
        for h in hits[:2]:
            h_file = Path(h.get("source_file", "")).stem.lower().replace(" ", "_")
            img_file = Path(meta.get("source_pdf", "")).stem.lower().replace(" ", "_")
            if h_file == img_file and abs((h.get("page_start") or 0) - meta.get("page", 0)) <= 1:
                provenance_boost = 0.05
                break

        composite = (norm_semantic * 0.60) + (cap_overlap * 0.25) + (kw_overlap * 0.15) + provenance_boost

        logger.info(
            "  [CANDIDATE] %s (p.%d): sem=%.3f, cap_ov=%.2f, kw_ov=%.2f, comp=%.3f | Cap='%s'",
            image_id, meta.get("page", 0), norm_semantic, cap_overlap, kw_overlap, composite, caption[:50]
        )

        # ── Stage C: Strict Confidence Threshold ──────────────────────
        # Must meet minimum semantic similarity
        if norm_semantic < MIN_SEMANTIC_SIM:
            continue

        # If no direct caption overlap, require higher semantic confidence
        effective_threshold = MIN_COMPOSITE_SCORE if cap_overlap > 0 else (MIN_COMPOSITE_SCORE + 0.08)
        if composite < effective_threshold:
            continue

        scored_candidates.append((composite, meta, caption))

    if not scored_candidates:
        logger.info("[image_retrieval] No candidate passed confidence thresholds; returning []")
        return []

    # Sort descending by composite score
    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    selected = scored_candidates[:MAX_RETURN_IMAGES]

    results = []
    for comp_score, meta, cap in selected:
        logger.info(
            "  [ACCEPTED] %s (p.%d, score=%.3f): %s",
            meta.get("image_id"), meta.get("page", 0), comp_score, cap[:60]
        )
        results.append({
            "image_id": meta.get("image_id", ""),
            "url": meta.get("url_path", ""),
            "source": meta.get("source_pdf", ""),
            "page": meta.get("page", 0),
            "caption": cap or meta.get("section_heading", ""),
        })

    return results


def _detect_domain(question: str, hits: list[dict]) -> str:
    """Determine whether the query is primarily Physics, Chemistry, or Biology."""
    q_low = question.lower()
    phys = sum(1 for w in _PHYSICS_TERMS if w in q_low)
    bio = sum(1 for w in _BIOLOGY_TERMS if w in q_low)
    chem = sum(1 for w in _CHEMISTRY_TERMS if w in q_low)

    # Check top text hits
    for h in hits[:2]:
        sub = (h.get("subject_area") or "").lower()
        if "physics" in sub:
            phys += 2
        elif "biology" in sub:
            bio += 2
        elif "chemistry" in sub:
            chem += 2

    if phys > bio and phys > chem and phys >= 1:
        return "Physics"
    if bio > phys and bio > chem and bio >= 1:
        return "Biology"
    if chem > phys and chem > bio and chem >= 1:
        return "Chemistry"

    return "Science"


def _extract_keywords(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def _overlap_ratio(query_keywords: set[str], text: str) -> float:
    if not query_keywords or not text:
        return 0.0
    text_low = text.lower()
    matches = sum(1 for kw in query_keywords if kw in text_low)
    return min(1.0, matches / max(1, len(query_keywords)))
