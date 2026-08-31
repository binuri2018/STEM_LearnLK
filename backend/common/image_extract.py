"""
Extract and index images from textbook PDFs with rich spatial context and dedicated vector embeddings.

Runs during ingest:
1. Spatially binds each image to its nearest caption, section heading, and surrounding text.
2. Infers subject discipline (Physics, Chemistry, Biology) and key science terms.
3. Builds a dedicated FAISS image vector index (`image_index.faiss` + `image_metadata.jsonl` + `image_index.json`).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypedDict

import faiss  # type: ignore
import fitz  # PyMuPDF
import numpy as np

from backend.common.config import settings
from backend.common.embeddings import embed_texts_for_ingest
from backend.common.metadata_infer import infer_from_path

# Minimum pixel dimensions to filter out tiny decorative artifacts
MIN_W = 80
MIN_H = 80
MAX_PER_PAGE = 20

# Stopwords for keyword extraction
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "what", "which", "who",
    "when", "where", "how", "why", "in", "on", "at", "to", "for", "of",
    "and", "or", "but", "not", "with", "from", "by", "as", "this", "that",
    "it", "its", "i", "you", "we", "they", "he", "she", "free", "distribution",
    "page", "let", "us", "following", "given", "figure", "fig", "diagram",
    "activity", "grade", "part", "science",
}

# Domain keyword lexicons for discipline detection
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


class ImageRecord(TypedDict):
    image_id: str
    file_path: str
    url_path: str
    source_pdf: str
    page: int
    grade: int | None
    subject_area: str
    section_heading: str
    caption: str
    nearby_text: str
    keywords: list[str]
    semantic_description: str
    bbox: list[float]


def extract_and_index_images(
    pdf_paths: list[Path],
    resource_dir: Path,
    data_dir: Path,
) -> list[ImageRecord]:
    """
    Extract images, build rich spatial metadata, compute embeddings,
    and save both the metadata JSON/JSONL and the dedicated FAISS index.
    """
    images_dir = data_dir / "extracted_images"
    images_dir.mkdir(parents=True, exist_ok=True)

    all_records: list[ImageRecord] = []
    seen_xrefs: set[str] = set()

    for pdf_path in pdf_paths:
        rel = str(pdf_path.relative_to(resource_dir)).replace("\\", "/")
        print(f"  [images] Scanning {rel} ...")
        try:
            records = _extract_from_pdf(pdf_path, rel, images_dir, seen_xrefs)
        except Exception as exc:
            print(f"  [images] Warning: could not extract images from {rel}: {exc}")
            records = []
        all_records.extend(records)
        print(f"  [images]   -> {len(records)} figures extracted")

    if not all_records:
        print("[images] No qualifying images found.")
        return []

    # 1. Save metadata JSON and JSONL
    index_path = data_dir / settings.index_manifest_name.replace("manifest", "image_manifest").replace("index_manifest.json", "image_index.json")
    if not index_path.name.endswith(".json"):
        index_path = data_dir / "image_index.json"
    with index_path.open("w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    meta_jsonl = data_dir / settings.image_metadata_name
    with meta_jsonl.open("w", encoding="utf-8") as f:
        for rec in all_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"[images] Saved {len(all_records)} image records to {index_path} and {meta_jsonl}")

    # 2. Embed semantic descriptions and build dedicated FAISS index
    print(f"[images] Embedding {len(all_records)} image descriptions for dedicated vector index ...")
    descriptions = [rec["semantic_description"] for rec in all_records]
    vectors = embed_texts_for_ingest(descriptions)

    dim = vectors.shape[1]
    image_index = faiss.IndexFlatIP(dim)
    image_index.add(vectors)

    faiss_path = data_dir / settings.image_faiss_index_name
    faiss.write_index(image_index, str(faiss_path))
    print(f"[images] Saved dedicated image FAISS index to {faiss_path}")

    return all_records


def _extract_from_pdf(
    pdf_path: Path,
    rel_source: str,
    images_dir: Path,
    seen_xrefs: set[str],
) -> list[ImageRecord]:
    doc = fitz.open(pdf_path)
    records: list[ImageRecord] = []
    pdf_stem = _safe_stem(rel_source)
    pdf_meta = infer_from_path(Path(rel_source))

    current_chapter_heading = ""

    try:
        for page_idx in range(len(doc)):
            page_num = page_idx + 1
            page = doc.load_page(page_idx)
            raw_blocks = page.get_text("blocks")
            text_blocks = [b for b in raw_blocks if len(b) > 4 and b[4].strip()]
            images = page.get_images(full=True)

            # Update running chapter / page header
            page_header = _detect_page_header(text_blocks)
            if page_header:
                current_chapter_heading = page_header

            # Filter + deduplicate
            seen_on_page: set[int] = set()
            good_images = []
            for img_tuple in images:
                xref = img_tuple[0]
                w, h = img_tuple[2], img_tuple[3]
                if w < MIN_W or h < MIN_H:
                    continue
                if xref in seen_on_page:
                    continue
                dedup_key = f"{pdf_stem}:{xref}"
                if dedup_key in seen_xrefs:
                    continue
                seen_on_page.add(xref)
                seen_xrefs.add(dedup_key)
                good_images.append((xref, w, h))

            good_images = good_images[:MAX_PER_PAGE]

            for xref, w, h in good_images:
                try:
                    record = _save_and_build_record(
                        doc=doc,
                        page=page,
                        xref=xref,
                        w=w,
                        h=h,
                        page_num=page_num,
                        text_blocks=text_blocks,
                        chapter_heading=current_chapter_heading,
                        pdf_stem=pdf_stem,
                        rel_source=rel_source,
                        pdf_grade=pdf_meta.grade,
                        images_dir=images_dir,
                    )
                    if record:
                        records.append(record)
                except Exception as exc:
                    print(f"    [images] Skip xref {xref} on page {page_num}: {exc}")
    finally:
        doc.close()

    return records


def _save_and_build_record(
    *,
    doc: fitz.Document,
    page: fitz.Page,
    xref: int,
    w: int,
    h: int,
    page_num: int,
    text_blocks: list[tuple],
    chapter_heading: str,
    pdf_stem: str,
    rel_source: str,
    pdf_grade: int | None,
    images_dir: Path,
) -> ImageRecord | None:
    image_id = f"{pdf_stem}_p{page_num}_x{xref}"
    out_path = images_dir / f"{image_id}.png"

    rects = page.get_image_rects(xref)
    if not rects:
        return None
    rect = rects[0]
    bbox = [rect.x0, rect.y0, rect.x1, rect.y1]

    # Save PNG
    if not out_path.exists():
        pix = fitz.Pixmap(doc, xref)
        if pix.n >= 4:
            pix_rgb = fitz.Pixmap(fitz.csRGB, pix)
            pix_rgb.save(str(out_path))
        else:
            pix.save(str(out_path))

    # Spatial text extraction
    caption, section_heading, nearby_text = _extract_spatial_context(
        rect, text_blocks, chapter_heading
    )

    # Inferred discipline (Physics, Chemistry, Biology, Science)
    subject_area = _infer_discipline(chapter_heading, section_heading, caption, nearby_text)

    # Extract keywords
    combined_raw = f"{section_heading} {caption} {nearby_text}"
    keywords = _extract_key_terms(combined_raw)

    # Construct rich semantic description for embedding
    desc_parts = []
    if subject_area:
        desc_parts.append(f"Subject: {subject_area}")
    if pdf_grade:
        desc_parts.append(f"Grade {pdf_grade}")
    if section_heading:
        desc_parts.append(f"Section: {section_heading}")
    if caption:
        desc_parts.append(f"Caption: {caption}")
    if nearby_text:
        desc_parts.append(f"Diagram Content: {nearby_text}")
    if keywords:
        desc_parts.append(f"Key concepts: {', '.join(keywords[:12])}")

    semantic_description = " | ".join(desc_parts)

    return ImageRecord(
        image_id=image_id,
        file_path=str(out_path),
        url_path=f"/images/{image_id}.png",
        source_pdf=rel_source,
        page=page_num,
        grade=pdf_grade,
        subject_area=subject_area,
        section_heading=section_heading,
        caption=caption,
        nearby_text=nearby_text,
        keywords=keywords,
        semantic_description=semantic_description,
        bbox=bbox,
    )


def _extract_spatial_context(
    img_rect: fitz.Rect,
    text_blocks: list[tuple],
    fallback_chapter: str,
) -> tuple[str, str, str]:
    """
    Find the spatially nearest caption, section header, and surrounding text
    for an image based on its bounding box coordinates.
    """
    caption = ""
    nearby_blocks: list[str] = []
    section_heading = fallback_chapter

    # Distance threshold: 80pt vertically
    for b in text_blocks:
        bx0, by0, bx1, by1, btext = b[0], b[1], b[2], b[3], b[4].strip()
        if not btext:
            continue

        # Calculate vertical distance to image
        if by1 < img_rect.y0:
            v_dist = img_rect.y0 - by1
            is_above = True
        elif by0 > img_rect.y1:
            v_dist = by0 - img_rect.y1
            is_above = False
        else:
            v_dist = 0
            is_above = False

        # If spatially adjacent (within 85pt)
        if v_dist <= 85:
            clean_b = " ".join(btext.split())
            # Skip mere page numbers or header artifacts
            if re.fullmatch(r"\d+", clean_b) or clean_b.lower() == "for free distribution":
                continue

            nearby_blocks.append(clean_b)

            # Check if this block contains a figure caption
            if not caption:
                for line in btext.splitlines():
                    low = line.lower()
                    if any(kw in low for kw in ("figure", "fig.", "diagram", "chart", "table")):
                        # Clean caption line
                        caption = " ".join(line.strip().split())
                        break

            # If above image and short, it might be a section heading
            if is_above and v_dist <= 50 and len(clean_b) < 60:
                if not any(k in clean_b.lower() for k in ("figure", "fig", "for free")):
                    section_heading = clean_b

    nearby_text = " ".join(nearby_blocks)[:350]
    return caption, section_heading, nearby_text


def _detect_page_header(text_blocks: list[tuple]) -> str:
    """Detect chapter or section heading from the top blocks of a page."""
    for b in text_blocks:
        by0, btext = b[1], b[4].strip()
        # Top of the page (y < 100 pt)
        if by0 < 100 and btext:
            clean = " ".join(btext.split())
            if len(clean) > 3 and not re.fullmatch(r"\d+", clean):
                if not clean.lower().startswith("for free"):
                    return clean
    return ""


def _infer_discipline(
    chapter: str,
    heading: str,
    caption: str,
    nearby: str,
) -> str:
    """Infer Physics, Chemistry, Biology, or Science from vocabulary."""
    combined = f"{chapter} {heading} {caption} {nearby}".lower()

    phys_count = sum(1 for kw in _PHYSICS_TERMS if kw in combined)
    bio_count = sum(1 for kw in _BIOLOGY_TERMS if kw in combined)
    chem_count = sum(1 for kw in _CHEMISTRY_TERMS if kw in combined)

    if phys_count > bio_count and phys_count > chem_count and phys_count >= 1:
        return "Physics"
    if bio_count > phys_count and bio_count > chem_count and bio_count >= 1:
        return "Biology"
    if chem_count > phys_count and chem_count > bio_count and chem_count >= 1:
        return "Chemistry"

    return "Science"


def _extract_key_terms(text: str) -> list[str]:
    """Extract distinct scientific keywords from text."""
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    seen: set[str] = set()
    terms: list[str] = []
    for w in words:
        if w not in _STOPWORDS and w not in seen:
            seen.add(w)
            terms.append(w)
    return terms


def _safe_stem(rel_path: str) -> str:
    stem = Path(rel_path).stem
    safe = "".join(c if c.isalnum() else "_" for c in stem)
    return safe.lower()
