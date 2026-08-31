"""In-process learning-state prediction (RandomForest, joblib).

Merges the former standalone ml-service ``modules/predict.py`` and the emotion
encoder so no second HTTP service is needed.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from backend.common.config import settings

logger = logging.getLogger(__name__)

_EMOTION_ENCODING = {
    "neutral": 0,
    "happy": 1,
    "confused": 2,
    "frustrated": 3,
    "surprised": 4,
}

_payload: Optional[dict] = None
_load_error: str | None = None


def encode_emotion(emotion: str) -> int:
    return _EMOTION_ENCODING.get((emotion or "").lower(), 0)


def _load_model() -> dict:
    global _payload, _load_error
    if _payload is not None:
        return _payload
    if _load_error is not None:
        raise FileNotFoundError(_load_error)

    path = settings.resolved_quiz_model_path()
    if not path.is_file():
        _load_error = f"Model file not found at {path}"
        raise FileNotFoundError(_load_error)

    import joblib  # deferred — heavy

    _payload = joblib.load(path)
    logger.info("Adaptive Quiz learning-state model loaded from %s", path)
    return _payload


def model_status() -> dict:
    path = settings.resolved_quiz_model_path()
    return {"path": str(path), "exists": path.is_file(), "loaded": _payload is not None, "error": _load_error}


def predict_learning_state(
    correctness: int,
    response_time: float,
    answer_changes: int,
    quiz_level: int,
    face_expression: str,
) -> dict:
    """Return ``{learningState, confidence, allProbabilities, inputFeatures}``."""
    payload = _load_model()
    model = payload["model"]
    le = payload["label_encoder"]

    expression_encoded = encode_emotion(face_expression)
    feature_vector = np.array([[
        int(correctness),
        float(response_time),
        int(answer_changes),
        int(quiz_level),
        int(expression_encoded),
    ]])

    predicted_index = model.predict(feature_vector)[0]
    predicted_label = le.inverse_transform([predicted_index])[0]
    class_probabilities = model.predict_proba(feature_vector)[0]

    all_probs = {
        le.inverse_transform([i])[0]: round(float(p), 4)
        for i, p in enumerate(class_probabilities)
    }
    confidence = round(float(class_probabilities[predicted_index]), 4)

    return {
        "learningState": predicted_label,
        "confidence": confidence,
        "allProbabilities": all_probs,
        "inputFeatures": {
            "correctness": correctness,
            "responseTime": response_time,
            "answerChanges": answer_changes,
            "quizLevel": quiz_level,
            "faceExpression": face_expression,
            "faceExpressionEncoded": expression_encoded,
        },
    }
