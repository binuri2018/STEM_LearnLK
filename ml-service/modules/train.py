"""
train.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Trains a Random Forest classifier to predict student learning state.

Input features:
    correctness      — 0 (wrong) or 1 (correct)
    responseTime     — seconds taken to answer
    answerChanges    — number of times student changed selection
    quizLevel        — 1, 2, or 3
    faceExpression   — encoded integer (see emotion_placeholder.py)

Output labels:
    strong_understanding
    partial_understanding
    weak_understanding
    needs_hint

HOW TO RETRAIN:
    1. Add more rows to  data/training_data.csv
    2. Run:  python modules/train.py
    3. The updated model is saved to  models/learning_state_model.pkl
    4. Restart the FastAPI server — it auto-loads the new model file.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import sys
import pandas as pd
import numpy as np
import joblib
from pathlib import Path

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, confusion_matrix

# ── Resolve Paths ─────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent.parent
DATA_PATH  = BASE_DIR / "data" / "training_data.csv"
MODEL_DIR  = BASE_DIR / "models"
MODEL_PATH = MODEL_DIR / "learning_state_model.pkl"

# Emotion encoding map (must match emotion_placeholder.py)
EMOTION_ENCODING = {
    "neutral": 0, "happy": 1, "confused": 2, "frustrated": 3, "surprised": 4
}

FEATURE_COLUMNS = ["correctness", "responseTime", "answerChanges", "quizLevel", "faceExpression"]
LABEL_COLUMN    = "label"


def load_and_preprocess(csv_path: Path) -> tuple:
    """
    Load CSV, encode the faceExpression column, and split into X / y.
    Returns (X, y, label_encoder).
    """
    print(f"Loading dataset from: {csv_path}")
    df = pd.read_csv(csv_path)

    print(f"   Rows loaded: {len(df)}")
    print(f"   Label distribution:\n{df[LABEL_COLUMN].value_counts().to_string()}\n")

    # Encode faceExpression string → integer
    df["faceExpression"] = df["faceExpression"].str.lower().map(EMOTION_ENCODING).fillna(0).astype(int)

    # Encode target labels
    le = LabelEncoder()
    y = le.fit_transform(df[LABEL_COLUMN])
    X = df[FEATURE_COLUMNS].values

    return X, y, le


def train_model(X: np.ndarray, y: np.ndarray) -> RandomForestClassifier:
    """
    Train a Random Forest classifier with cross-validation reporting.
    """
    print("Training Random Forest Classifier ...")

    model = RandomForestClassifier(
        n_estimators=200,       # 200 decision trees
        max_depth=8,            # Limit depth to prevent overfitting on small dataset
        min_samples_split=2,
        min_samples_leaf=1,
        class_weight="balanced",  # Handle class imbalance automatically
        random_state=42,
    )

    # 5-fold cross-validation accuracy
    cv_scores = cross_val_score(model, X, y, cv=5, scoring="accuracy")
    print(f"   Cross-validation accuracy: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")

    # Train on full dataset for deployment
    model.fit(X, y)
    print(f"   Feature importances:")
    for name, imp in zip(FEATURE_COLUMNS, model.feature_importances_):
        print(f"     {name:<18} {imp:.4f}")

    return model


def evaluate_model(model: RandomForestClassifier, X: np.ndarray, y: np.ndarray, le: LabelEncoder):
    """
    Evaluate on a held-out test split and print classification report.
    """
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    model_copy = RandomForestClassifier(**model.get_params())
    model_copy.fit(X_train, y_train)
    y_pred = model_copy.predict(X_test)

    print("\nClassification Report (20% held-out test set):")
    print(classification_report(y_test, y_pred, target_names=le.classes_))
    print("Confusion Matrix:")
    print(confusion_matrix(y_test, y_pred))


def save_model(model: RandomForestClassifier, le: LabelEncoder):
    """
    Save the trained model and label encoder together using joblib.
    """
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"model": model, "label_encoder": le, "feature_columns": FEATURE_COLUMNS}
    joblib.dump(payload, MODEL_PATH)
    print(f"\nModel saved to: {MODEL_PATH}")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not DATA_PATH.exists():
        print(f"Dataset not found at {DATA_PATH}")
        sys.exit(1)

    X, y, le = load_and_preprocess(DATA_PATH)
    model     = train_model(X, y)
    evaluate_model(model, X, y, le)
    save_model(model, le)

    print("\nTraining complete! Restart the FastAPI server to load the new model.")
