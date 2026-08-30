"""Train the Narrative Learning persona classifier.

Mix a Google Form export with optional existing/synthetic rows.
Theme must come from the student's story-style answers, not from Interest alone.

Usage:
  python scripts/train_persona.py --survey path/to/form.csv
  python scripts/train_persona.py --base sri_lankan_student.csv --survey form.csv --out-dir backend/components/narrative_learning
"""
from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import LabelEncoder

THEME_FROM_STYLE = {
    "a match, a race, or a team trying to win": "Action & Competition",
    "action & competition": "Action & Competition",
    "music, art, dance, or making something": "Creative Expression",
    "creative expression": "Creative Expression",
    "robots, coding, gadgets, or the future": "Sci-Fi & Innovation",
    "sci-fi & innovation": "Sci-Fi & Innovation",
    "forests, animals, hospitals, or the environment": "Nature & Discovery",
    "nature & discovery": "Nature & Discovery",
    "a puzzle, a mystery, or solving a case with clues": "Logic & Mystery",
    "logic & mystery": "Logic & Mystery",
}

STRUGGLE_MAP = {
    "i usually understand it": "Low",
    "low": "Low",
    "i understand some parts, some parts are hard": "Medium",
    "medium": "Medium",
    "i often find it hard": "High",
    "high": "High",
}


def _norm(value) -> str:
    return str(value or "").strip().lower()


def _pick_col(df: pd.DataFrame, *needles: str) -> str | None:
    lower = {c.lower(): c for c in df.columns}
    for needle in needles:
        for key, orig in lower.items():
            if needle in key:
                return orig
    return None


def load_base(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    need = ["Interest", "Aspiration", "Story_Theme"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise SystemExit(f"{path} missing columns: {missing}")
    if "Struggle_Level" not in df.columns:
        df["Struggle_Level"] = "Medium"
    return df[["Interest", "Aspiration", "Struggle_Level", "Story_Theme"]].copy()


def load_survey(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path)
    interest = _pick_col(raw, "enjoy", "interest", "free time")
    aspiration = _pick_col(raw, "job", "aspiration", "career")
    struggle = _pick_col(raw, "science feel", "struggle", "how does school science")
    theme_a = _pick_col(raw, "which style", "story style", "short story")
    theme_b = _pick_col(raw, "which opening", "opening would")
    if not interest or not aspiration or not theme_a:
        raise SystemExit(
            f"Could not find Interest / Aspiration / theme columns in {path}. "
            f"Columns: {list(raw.columns)}"
        )

    rows = []
    for _, row in raw.iterrows():
        t1 = THEME_FROM_STYLE.get(_norm(row[theme_a]), str(row[theme_a]).strip())
        if theme_b:
            t2 = THEME_FROM_STYLE.get(_norm(row[theme_b]), str(row[theme_b]).strip())
            if t1 != t2:
                continue
        struggle_val = "Medium"
        if struggle:
            struggle_val = STRUGGLE_MAP.get(_norm(row[struggle]), str(row[struggle]).strip() or "Medium")
        rows.append({
            "Interest": str(row[interest]).strip(),
            "Aspiration": str(row[aspiration]).strip(),
            "Struggle_Level": struggle_val,
            "Story_Theme": t1,
        })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, help="Existing CSV with Interest,Aspiration,Story_Theme")
    parser.add_argument("--survey", type=Path, help="Google Form export")
    parser.add_argument("--out-dir", type=Path, default=Path("backend/components/narrative_learning"))
    args = parser.parse_args()

    frames = []
    if args.base and args.base.is_file():
        frames.append(load_base(args.base))
    if args.survey and args.survey.is_file():
        frames.append(load_survey(args.survey))
    if not frames:
        raise SystemExit("Provide --base and/or --survey CSV.")

    df = pd.concat(frames, ignore_index=True).dropna(subset=["Interest", "Aspiration", "Story_Theme"])
    print(f"Training rows: {len(df)}")
    print(df.groupby("Story_Theme").size())

    le_interest = LabelEncoder()
    le_aspiration = LabelEncoder()
    le_theme = LabelEncoder()
    X = pd.DataFrame({
        "Interest_Encoded": le_interest.fit_transform(df["Interest"]),
        "Aspiration_Encoded": le_aspiration.fit_transform(df["Aspiration"]),
    })
    y = le_theme.fit_transform(df["Story_Theme"])
    clf = RandomForestClassifier(n_estimators=200, random_state=42, max_depth=6)
    clf.fit(X, y)
    if len(df) >= 10:
        scores = cross_val_score(clf, X, y, cv=min(5, df["Story_Theme"].nunique()))
        print(f"CV accuracy: {scores.mean()*100:.1f}% ± {scores.std()*100:.1f}%")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    with open(args.out_dir / "persona_model.pkl", "wb") as f:
        pickle.dump(clf, f)
    with open(args.out_dir / "encoder.pkl", "wb") as f:
        pickle.dump({"interest": le_interest, "aspiration": le_aspiration, "theme": le_theme}, f)
    print(f"Wrote {args.out_dir / 'persona_model.pkl'} and encoder.pkl")


if __name__ == "__main__":
    main()
