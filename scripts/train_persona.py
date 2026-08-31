"""Train the Narrative Learning persona classifier by hand.

Mix the Google Form (~30 real answers) with the synthetic Sri Lankan student
rows. Theme comes from the student's story-style answers, not from Interest
alone.

Usage (from STEM_LearnLK):

  python scripts/train_persona.py --survey path/to/form.xlsx --preview
  python scripts/train_persona.py --survey path/to/form.xlsx

Writes persona_model.pkl + encoder.pkl next to the classifier, plus a cleaned
CSV you can inspect.
"""
from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.preprocessing import LabelEncoder

THEMES = [
    "Action & Competition",
    "Creative Expression",
    "Sci-Fi & Innovation",
    "Nature & Discovery",
    "Logic & Mystery",
]

INTEREST_CANON = {
    "cricket": "Cricket",
    "volleyball": "Volleyball",
    "volleyball / other sport": "Volleyball",
    "gaming": "Gaming",
    "mobile gaming": "Gaming",
    "mobile gaming (pubg/freefire)": "Gaming",
    "mobile gaming (pubg, free fire)": "Gaming",
    "mobile gaming (pubg, free fire, esports)": "Gaming",
    "pubg": "Gaming",
    "free fire": "Gaming",
    "music": "Music",
    "kandyan dancing": "Kandyan Dancing",
    "kandyan / traditional dancing": "Kandyan Dancing",
    "art": "Art",
    "art or drawing": "Art",
    "graphic design": "Art",
    "photography": "Photography",
    "photography or graphic design": "Photography",
    "reading": "Reading",
    "nature": "Nature",
    "nature / environment": "Nature",
    "environmental science": "Nature",
    "biology": "Nature",
    "robotics": "Robotics",
    "coding/ict": "Coding/ICT",
    "coding / ict": "Coding/ICT",
    "mathematics": "Mathematics",
    "astronomy": "Astronomy",
    "astronomy / space": "Astronomy",
}

ASPIRATION_CANON = {
    "doctor": "Doctor",
    "doctor / health": "Doctor",
    "engineer": "Engineer",
    "engineer (civil, mechanical, software, etc.)": "Engineer",
    "civil engineer": "Engineer",
    "software engineer": "Engineer",
    "scientist": "Scientist",
    "scientist / researcher": "Scientist",
    "data scientist": "Scientist",
    "teacher": "Teacher",
    "athlete": "Athlete",
    "athlete / sports": "Athlete",
    "artist": "Artist",
    "artist / designer / musician": "Artist",
    "graphic designer": "Artist",
    "architect": "Architect",
    "pilot": "Pilot",
    "entrepreneur": "Entrepreneur",
    "entrepreneur / business": "Entrepreneur",
}

THEME_FROM_STYLE = {
    "a match, a race, or a team trying to win": "Action & Competition",
    "action & competition": "Action & Competition",
    "action": "Action & Competition",
    "it was the last over. one wicket. the whole ground went quiet.": "Action & Competition",
    "music, art, dance, or making something": "Creative Expression",
    "creative expression": "Creative Expression",
    "creative": "Creative Expression",
    "she tuned the violin once more, then listened for the pattern in the sound.": "Creative Expression",
    "robots, coding, gadgets, or the future": "Sci-Fi & Innovation",
    "sci-fi & innovation": "Sci-Fi & Innovation",
    "scifi": "Sci-Fi & Innovation",
    "sci-fi": "Sci-Fi & Innovation",
    "the small robot stalled in the school lab. they had ten minutes before the demo.": "Sci-Fi & Innovation",
    "forests, animals, hospitals, or the environment": "Nature & Discovery",
    "nature & discovery": "Nature & Discovery",
    "nature": "Nature & Discovery",
    "at the paddy field, the water was lower than last week. something had changed.": "Nature & Discovery",
    "a puzzle, a mystery, or solving a case with clues": "Logic & Mystery",
    "logic & mystery": "Logic & Mystery",
    "logic": "Logic & Mystery",
    "a notebook was missing from the lab. only the numbers on the board made sense.": "Logic & Mystery",
}

STRUGGLE_MAP = {
    "i usually understand it": "Low",
    "i usually understand it (we code as low)": "Low",
    "low": "Low",
    "i understand some parts, some parts are hard": "Medium",
    "i understand some parts; some are hard": "Medium",
    "medium": "Medium",
    "i often find it hard": "High",
    "high": "High",
}

_REPO = Path(__file__).resolve().parents[1]
_STEM_TEXT_CSV = Path(r"C:\STEM TEXT\sri_lankan_student.csv")
DEFAULT_BASE = Path(__file__).with_name("sri_lankan_student.csv")
DEFAULT_OUT = _REPO / "backend" / "components" / "narrative_learning"


def _norm(value) -> str:
    text = str(value or "").strip().lower()
    for ch in "“”\"'‘’":
        text = text.replace(ch, "")
    return " ".join(text.replace("\n", " ").split())


def _map_lookup(table: dict[str, str], value) -> str | None:
    key = _norm(value)
    if not key or key in {"nan", "none", "null"}:
        return None
    if key in table:
        return table[key]
    for needle, canon in table.items():
        if needle in key or key in needle:
            return canon
    return None


def _pick_col(df: pd.DataFrame, *needles: str) -> str | None:
    lower = {str(c).lower(): c for c in df.columns}
    for needle in needles:
        for key, orig in lower.items():
            if needle in key:
                return orig
    return None


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        return pd.read_excel(path, engine="openpyxl")
    if suffix == ".xls":
        try:
            return pd.read_excel(path, engine="xlrd")
        except Exception:
            return pd.read_excel(path)
    return pd.read_csv(path)


def canonicalize_frame(df: pd.DataFrame, source: str) -> pd.DataFrame:
    rows = []
    dropped_other = 0
    for _, row in df.iterrows():
        interest = _map_lookup(INTEREST_CANON, row.get("Interest"))
        aspiration = _map_lookup(ASPIRATION_CANON, row.get("Aspiration"))
        theme = _map_lookup(THEME_FROM_STYLE, row.get("Story_Theme")) or str(row.get("Story_Theme") or "").strip()
        if theme not in THEMES:
            continue
        if not interest or not aspiration:
            dropped_other += 1
            continue
        struggle = _map_lookup(STRUGGLE_MAP, row.get("Struggle_Level")) or "Medium"
        rows.append({
            "Interest": interest,
            "Aspiration": aspiration,
            "Struggle_Level": struggle,
            "Story_Theme": theme,
            "source": source,
        })
    out = pd.DataFrame(rows)
    if dropped_other:
        print(f"  dropped {dropped_other} {source} rows with Interest/Aspiration='Other' or unknown")
    return out


def load_base(path: Path) -> pd.DataFrame:
    df = read_table(path)
    need = ["Interest", "Aspiration", "Story_Theme"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise SystemExit(f"{path} missing columns: {missing}")
    if "Struggle_Level" not in df.columns:
        df["Struggle_Level"] = "Medium"
    return canonicalize_frame(df, "synthetic")


def load_survey(path: Path, drop_mismatch: bool) -> pd.DataFrame:
    raw = read_table(path)
    print(f"Survey columns ({path.name}):")
    for col in raw.columns:
        print(f"  - {col}")

    interest = _pick_col(raw, "enjoy", "free time", "interest")
    aspiration = _pick_col(raw, "job", "hope to have", "aspiration", "career")
    struggle = _pick_col(raw, "science feel", "struggle", "school science")
    theme_a = _pick_col(raw, "which style", "short story", "story style")
    theme_b = _pick_col(raw, "which opening", "keep reading", "opening would")
    if not interest or not aspiration or not theme_a:
        raise SystemExit(
            f"Could not find Interest / Aspiration / story-style columns in {path}. "
            f"Columns: {list(raw.columns)}"
        )
    print(f"Mapped columns: interest={interest!r}, aspiration={aspiration!r}, "
          f"style={theme_a!r}, opening={theme_b!r}, struggle={struggle!r}")

    rows = []
    mismatch = 0
    for _, row in raw.iterrows():
        t1 = _map_lookup(THEME_FROM_STYLE, row[theme_a])
        t2 = _map_lookup(THEME_FROM_STYLE, row[theme_b]) if theme_b else t1
        if not t1:
            continue
        if t2 and t1 != t2:
            mismatch += 1
            if drop_mismatch:
                continue
        theme = t1 if (not t2 or t1 == t2) else t1
        interest_v = _map_lookup(INTEREST_CANON, row[interest])
        aspiration_v = _map_lookup(ASPIRATION_CANON, row[aspiration])
        if not interest_v or not aspiration_v:
            continue
        struggle_v = "Medium"
        if struggle:
            struggle_v = _map_lookup(STRUGGLE_MAP, row[struggle]) or "Medium"
        rows.append({
            "Interest": interest_v,
            "Aspiration": aspiration_v,
            "Struggle_Level": struggle_v,
            "Story_Theme": theme,
            "source": "survey",
        })
    print(f"Style vs opening mismatches: {mismatch} "
          f"({'dropped' if drop_mismatch else 'kept, labelled from style question'})")
    return pd.DataFrame(rows)


def resolve_base(path: Path | None) -> Path | None:
    candidates = [p for p in (path, DEFAULT_BASE, _STEM_TEXT_CSV) if p]
    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--survey", type=Path, help="Google Form export (.xlsx / .xls / .csv)")
    parser.add_argument("--base", type=Path, help="Synthetic CSV (default: scripts/sri_lankan_student.csv)")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--preview", action="store_true", help="Print recoded rows; do not train")
    parser.add_argument("--drop-mismatch", action="store_true",
                        help="Drop rows where style and opening disagree (default: keep, use style)")
    parser.add_argument("--survey-weight", type=float, default=3.0,
                        help="Weight for each real survey row (default 3 so ~30 rows are not drowned)")
    parser.add_argument("--synthetic-weight", type=float, default=1.0)
    parser.add_argument("--no-synthetic", action="store_true", help="Train on survey rows only")
    args = parser.parse_args()

    frames = []
    if not args.no_synthetic:
        base = resolve_base(args.base)
        if not base:
            raise SystemExit("No synthetic CSV found. Pass --base or copy sri_lankan_student.csv next to this script.")
        print(f"Synthetic: {base}")
        frames.append(load_base(base))
    if args.survey:
        if not args.survey.is_file():
            raise SystemExit(f"Survey file not found: {args.survey}")
        frames.append(load_survey(args.survey, drop_mismatch=args.drop_mismatch))
    if not frames:
        raise SystemExit("Provide --survey and/or synthetic --base.")

    df = pd.concat(frames, ignore_index=True).dropna(subset=["Interest", "Aspiration", "Story_Theme"])
    print(f"\nTraining rows: {len(df)}")
    print(df.groupby(["source", "Story_Theme"]).size().unstack(fill_value=0))
    print("\nInterest x theme:")
    print(pd.crosstab(df["Interest"], df["Story_Theme"]))

    cleaned = args.out_dir / "training_rows.csv"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(cleaned, index=False)
    print(f"\nWrote cleaned rows to {cleaned}")

    if args.preview:
        print("Preview only — no model written.")
        return

    if df["Story_Theme"].nunique() < 2:
        raise SystemExit("Need at least two theme classes to train.")

    le_interest = LabelEncoder()
    le_aspiration = LabelEncoder()
    le_theme = LabelEncoder()
    X = pd.DataFrame({
        "Interest_Encoded": le_interest.fit_transform(df["Interest"]),
        "Aspiration_Encoded": le_aspiration.fit_transform(df["Aspiration"]),
    })
    y = le_theme.fit_transform(df["Story_Theme"])
    weights = np.where(
        df["source"].eq("survey"),
        args.survey_weight,
        args.synthetic_weight,
    )

    clf = RandomForestClassifier(
        n_estimators=200,
        random_state=42,
        max_depth=5,
        class_weight="balanced",
        min_samples_leaf=2,
    )
    clf.fit(X, y, sample_weight=weights)
    print(f"\nTrain accuracy (weighted fit, unweighted score): {clf.score(X, y)*100:.1f}%")

    n_classes = df["Story_Theme"].nunique()
    min_class = int(df["Story_Theme"].value_counts().min())
    if len(df) >= 15 and min_class >= 2:
        folds = min(5, min_class)
        cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=42)
        scores = cross_val_score(clf, X, y, cv=cv)
        print(f"CV accuracy: {scores.mean()*100:.1f}% ± {scores.std()*100:.1f}%  ({folds}-fold)")
    else:
        print("Skipped CV (a theme has fewer than 2 rows).")

    print("Theme classes:", list(le_theme.classes_))
    with open(args.out_dir / "persona_model.pkl", "wb") as f:
        pickle.dump(clf, f)
    with open(args.out_dir / "encoder.pkl", "wb") as f:
        pickle.dump({"interest": le_interest, "aspiration": le_aspiration, "theme": le_theme}, f)
    print(f"Wrote {args.out_dir / 'persona_model.pkl'} and encoder.pkl")
    print("Then set USE_TRAINED_CLASSIFIER=1 in .env and restart the app.")


if __name__ == "__main__":
    main()
