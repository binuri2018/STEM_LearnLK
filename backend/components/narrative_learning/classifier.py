"""Single-output narrative classifier: answers -> Story_Theme.

Demo (default): use the student's story-style answer as the class.
After survey data is collected, train persona_model.pkl and set
USE_TRAINED_CLASSIFIER=1 — this file is the only switch.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

from backend.components.narrative_learning.model_config import _COMPONENT_DIR, _REPO_ROOT

# One output class for the whole pipeline
OUTPUT_LABEL = "Story_Theme"

THEMES = [
    "Action & Competition",
    "Creative Expression",
    "Sci-Fi & Innovation",
    "Nature & Discovery",
    "Logic & Mystery",
]

# Demo: one fixed class if the student skips the style question
DEMO_THEME = os.getenv("NARRATIVE_DEMO_THEME", "Action & Competition").strip() or THEMES[0]
USE_TRAINED = os.getenv("USE_TRAINED_CLASSIFIER", "").strip().lower() in {"1", "true", "yes"}

STYLE_TO_THEME = {
    "action": "Action & Competition",
    "creative": "Creative Expression",
    "scifi": "Sci-Fi & Innovation",
    "nature": "Nature & Discovery",
    "logic": "Logic & Mystery",
}

THEME_BLURBS = {
    "Action & Competition": "Your story will feel like a match — a goal, a team, and a bit of nerves.",
    "Creative Expression": "Your story will feel like making something — music, colour, or a performance.",
    "Sci-Fi & Innovation": "Your story will feel like a lab or a gadget — robots, code, and clever fixes.",
    "Nature & Discovery": "Your story will feel like being outdoors — plants, animals, or helping someone feel better.",
    "Logic & Mystery": "Your story will feel like a puzzle — clues, numbers, and a case to solve.",
}

SURVEY_LOG = Path(os.getenv("NARRATIVE_SURVEY_LOG") or os.path.join(_REPO_ROOT, "data", "narrative_survey.csv"))


def survey_spec() -> dict:
    """Questions shown before story generation (same as the Google Form)."""
    return {
        "output_label": OUTPUT_LABEL,
        "themes": THEMES,
        "theme_blurbs": THEME_BLURBS,
        "classifier_mode": "trained" if USE_TRAINED else "demo",
        "questions": [
            {
                "id": "grade",
                "prompt": "Which grade are you in?",
                "type": "choice",
                "options": [{"value": "10", "label": "Grade 10"}, {"value": "11", "label": "Grade 11"}],
            },
            {
                "id": "interest",
                "prompt": "What do you enjoy most in your free time?",
                "type": "choice",
                "options": [
                    {"value": "Cricket", "label": "Cricket"},
                    {"value": "Volleyball", "label": "Volleyball / other sport"},
                    {"value": "Gaming", "label": "Mobile gaming (PUBG, Free Fire)"},
                    {"value": "Music", "label": "Music"},
                    {"value": "Kandyan Dancing", "label": "Kandyan / traditional dancing"},
                    {"value": "Art", "label": "Art or drawing"},
                    {"value": "Photography", "label": "Photography or graphic design"},
                    {"value": "Reading", "label": "Reading"},
                    {"value": "Nature", "label": "Nature / environment"},
                    {"value": "Robotics", "label": "Robotics"},
                    {"value": "Coding/ICT", "label": "Coding / ICT"},
                    {"value": "Mathematics", "label": "Mathematics"},
                    {"value": "Astronomy", "label": "Astronomy / space"},
                ],
            },
            {
                "id": "aspiration",
                "prompt": "What job do you hope to have one day?",
                "type": "choice",
                "options": [
                    {"value": "Doctor", "label": "Doctor / health"},
                    {"value": "Engineer", "label": "Engineer"},
                    {"value": "Scientist", "label": "Scientist / researcher"},
                    {"value": "Teacher", "label": "Teacher"},
                    {"value": "Athlete", "label": "Athlete / sports"},
                    {"value": "Artist", "label": "Artist / designer / musician"},
                    {"value": "Architect", "label": "Architect"},
                    {"value": "Pilot", "label": "Pilot"},
                    {"value": "Entrepreneur", "label": "Entrepreneur / business"},
                ],
            },
            {
                "id": "struggle_level",
                "prompt": "How does school science feel for you right now?",
                "type": "choice",
                "options": [
                    {"value": "Low", "label": "I usually understand it"},
                    {"value": "Medium", "label": "I understand some parts; some are hard"},
                    {"value": "High", "label": "I often find it hard"},
                ],
            },
            {
                "id": "story_style",
                "prompt": "If science was a short story, which style would you actually want to read?",
                "type": "choice",
                "options": [
                    {"value": "action", "label": "A match, a race, or a team trying to win"},
                    {"value": "creative", "label": "Music, art, dance, or making something"},
                    {"value": "scifi", "label": "Robots, coding, gadgets, or the future"},
                    {"value": "nature", "label": "Forests, animals, hospitals, or the environment"},
                    {"value": "logic", "label": "A puzzle, a mystery, or solving a case with clues"},
                ],
            },
            {
                "id": "story_opening",
                "prompt": "Which opening would make you keep reading?",
                "type": "choice",
                "options": [
                    {"value": "action", "label": "It was the last over. One wicket. The whole ground went quiet."},
                    {"value": "creative", "label": "She tuned the violin once more, then listened for the pattern in the sound."},
                    {"value": "scifi", "label": "The small robot stalled in the school lab. They had ten minutes before the demo."},
                    {"value": "nature", "label": "At the paddy field, the water was lower than last week. Something had changed."},
                    {"value": "logic", "label": "A notebook was missing from the lab. Only the numbers on the board made sense."},
                ],
            },
        ],
    }


def _theme_from_style(style: str | None) -> str | None:
    if not style:
        return None
    key = str(style).strip().lower()
    if key in STYLE_TO_THEME:
        return STYLE_TO_THEME[key]
    for theme in THEMES:
        if key == theme.lower():
            return theme
    return None


def _canon_label(value: str, classes) -> str:
    raw = (value or "").strip()
    if raw in classes:
        return raw
    key = raw.lower()
    for label in classes:
        if key == str(label).lower():
            return str(label)
    return raw


def _predict_trained(interest: str, aspiration: str) -> str | None:
    pkl = Path(_COMPONENT_DIR) / "persona_model.pkl"
    enc = Path(_COMPONENT_DIR) / "encoder.pkl"
    if not pkl.is_file() or not enc.is_file():
        return None
    import pickle

    import pandas as pd

    with open(pkl, "rb") as f:
        model = pickle.load(f)
    with open(enc, "rb") as f:
        encoders = pickle.load(f)
    try:
        interest = _canon_label(interest, encoders["interest"].classes_)
        aspiration = _canon_label(aspiration, encoders["aspiration"].classes_)
        i_enc = encoders["interest"].transform([interest])[0]
        a_enc = encoders["aspiration"].transform([aspiration])[0]
        pred = model.predict(pd.DataFrame([[i_enc, a_enc]], columns=["Interest_Encoded", "Aspiration_Encoded"]))
        return str(encoders["theme"].inverse_transform(pred)[0])
    except Exception:
        return None


def classify(answers: dict) -> dict:
    """Return one Story_Theme. Demo uses the style question; trained uses the RF."""
    interest = (answers.get("interest") or "").strip()
    aspiration = (answers.get("aspiration") or "").strip()
    style = answers.get("story_style")
    opening = answers.get("story_opening")

    method = "demo"
    theme = None

    if USE_TRAINED:
        theme = _predict_trained(interest, aspiration)
        if theme:
            method = "trained"

    if not theme:
        t1 = _theme_from_style(style)
        t2 = _theme_from_style(opening)
        if t1 and t2 and t1 == t2:
            theme = t1
            method = "demo"
        elif t1:
            theme = t1
            method = "demo"
        else:
            theme = DEMO_THEME
            method = "demo-default"

    result = {
        "theme": theme,
        "blurb": THEME_BLURBS.get(theme, ""),
        "output_label": OUTPUT_LABEL,
        "method": method,
        "interest": interest,
        "aspiration": aspiration,
        "struggle_level": (answers.get("struggle_level") or "Medium").strip() or "Medium",
        "grade": str(answers.get("grade") or "").strip(),
    }
    _append_survey_log(answers, result)
    return result


def _append_survey_log(answers: dict, result: dict) -> None:
    try:
        SURVEY_LOG.parent.mkdir(parents=True, exist_ok=True)
        write_header = not SURVEY_LOG.is_file()
        with open(SURVEY_LOG, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "timestamp",
                    "Grade",
                    "Interest",
                    "Aspiration",
                    "Struggle_Level",
                    "story_style",
                    "story_opening",
                    "Story_Theme",
                    "method",
                ],
            )
            if write_header:
                writer.writeheader()
            writer.writerow({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "Grade": result.get("grade"),
                "Interest": result.get("interest"),
                "Aspiration": result.get("aspiration"),
                "Struggle_Level": result.get("struggle_level"),
                "story_style": answers.get("story_style"),
                "story_opening": answers.get("story_opening"),
                "Story_Theme": result.get("theme"),
                "method": result.get("method"),
            })
    except OSError:
        pass


def log_theme_feedback(theme: str, matched: bool, interest: str = "", aspiration: str = "") -> None:
    path = SURVEY_LOG.parent / "narrative_theme_feedback.csv"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not path.is_file()
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["timestamp", "Story_Theme", "matched", "Interest", "Aspiration"],
            )
            if write_header:
                writer.writeheader()
            writer.writerow({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "Story_Theme": theme,
                "matched": "yes" if matched else "no",
                "Interest": interest,
                "Aspiration": aspiration,
            })
    except OSError:
        pass
