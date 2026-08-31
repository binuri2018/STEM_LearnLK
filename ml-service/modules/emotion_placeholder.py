"""
emotion_placeholder.py — Real emotion detection via HuggingFace ViT + OpenCV.

Primary:  transformers pipeline (trpakov/vit-face-expression, PyTorch, no TensorFlow)
          + OpenCV Haar cascade for face crop (improves accuracy on webcam frames).
Fallback: Weighted random simulation if model not loaded or inference fails.

Model downloads automatically on first call (~330 MB, cached in ~/.cache/huggingface).
No extra pip install needed — transformers, torch, and opencv-python are already present.
"""

import random
import base64

SUPPORTED_EMOTIONS = ["neutral", "happy", "confused", "frustrated", "surprised"]

_SIMULATION_WEIGHTS = [0.35, 0.30, 0.20, 0.10, 0.05]

# Map HuggingFace FER labels → system labels
_LABEL_MAP = {
    "angry":    "frustrated",
    "disgust":  "frustrated",
    "fear":     "confused",
    "happy":    "happy",
    "neutral":  "neutral",
    "sad":      "confused",
    "surprise": "surprised",
}

_pipe         = None   # transformers pipeline — lazy loaded on first call
_face_cascade = None   # OpenCV Haar cascade — lazy loaded on first call


def _get_pipe():
    global _pipe
    if _pipe is None:
        from transformers import pipeline
        print("Loading emotion model (first call — ~30s)...")
        _pipe = pipeline(
            "image-classification",
            model="trpakov/vit-face-expression",
            top_k=1,
            device=-1,   # CPU
        )
        print("Emotion model ready.")
    return _pipe


def _get_cascade():
    global _face_cascade
    if _face_cascade is None:
        import cv2
        _face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
    return _face_cascade


def _simulate() -> tuple[str, float]:
    emotion    = random.choices(SUPPORTED_EMOTIONS, weights=_SIMULATION_WEIGHTS, k=1)[0]
    confidence = round(random.uniform(0.60, 0.92), 4)
    return emotion, confidence


def detect_emotion(frame_b64: str = "") -> tuple[str, float]:
    """
    Analyse a webcam frame and return (emotion_label, confidence).

    Parameters
    ----------
    frame_b64 : str
        Base64-encoded JPEG/PNG frame from the student's webcam.

    Returns
    -------
    tuple[str, float]
        (emotion, confidence) where emotion is one of SUPPORTED_EMOTIONS
        and confidence is in [0.0, 1.0].
    """
    if not frame_b64:
        return _simulate()

    try:
        import cv2
        import numpy as np
        from PIL import Image

        img_bytes = base64.b64decode(frame_b64)
        nparr     = np.frombuffer(img_bytes, np.uint8)
        bgr       = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if bgr is None:
            return _simulate()

        # Crop to face region for better classification accuracy
        gray  = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        faces = _get_cascade().detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48)
        )
        roi = bgr[faces[0][1]:faces[0][1]+faces[0][3], faces[0][0]:faces[0][0]+faces[0][2]] \
              if len(faces) > 0 else bgr

        pil_img = Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
        result  = _get_pipe()(pil_img)
        label   = result[0]["label"].lower()
        score   = result[0]["score"]
        return _LABEL_MAP.get(label, "neutral"), round(score, 4)

    except Exception:
        return _simulate()


def encode_emotion(emotion: str) -> int:
    """Encode an emotion label to an integer ML feature."""
    encoding = {
        "neutral":    0,
        "happy":      1,
        "confused":   2,
        "frustrated": 3,
        "surprised":  4,
    }
    return encoding.get(emotion.lower(), 0)
