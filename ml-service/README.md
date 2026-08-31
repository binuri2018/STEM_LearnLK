# ML Service — Setup & Usage Guide

## Overview
FastAPI service that provides:
1. **`POST /predict`** — learning-state classification using a trained Random Forest model  
2. **`POST /detect-emotion`** — facial expression detection (placeholder, plug-in ready)

---

## Setup

### 1. Create a virtual environment
```bash
cd ml-service
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Train the model (first time)
```bash
python modules/train.py
```
This reads `data/training_data.csv`, trains the Random Forest, and saves the model to `models/learning_state_model.pkl`.

### 4. Start the service
```bash
uvicorn main:app --reload --port 8000
```
Service will be available at `http://localhost:8000`  
Interactive docs (Swagger UI): `http://localhost:8000/docs`

---

## Retraining the Model

### When to retrain
- After collecting real student response data
- When adding more training samples to improve accuracy
- When adjusting label definitions

### Steps
1. Add new rows to `data/training_data.csv` following the format:
   ```
   correctness,responseTime,answerChanges,quizLevel,faceExpression,label
   1,12,0,2,neutral,strong_understanding
   0,40,4,3,frustrated,needs_hint
   ```

2. Run the training script:
   ```bash
   python modules/train.py
   ```

3. The script will print cross-validation accuracy, feature importances, and a classification report.

4. Restart the FastAPI server — it loads the new model automatically:
   ```bash
   uvicorn main:app --reload --port 8000
   ```

---

## Plugging in a Real Emotion Detection Model

Currently `modules/emotion_placeholder.py` returns a simulated emotion label.

### To replace with MediaPipe / DeepFace / CNN:

1. Install your model library:
   ```bash
   pip install deepface   # or mediapipe, tensorflow, etc.
   ```

2. Open `modules/emotion_placeholder.py` and replace the body of `detect_emotion()`:
   ```python
   # Example using DeepFace
   from deepface import DeepFace
   import base64, numpy as np, cv2

   def detect_emotion(frame_b64: str) -> str:
       img_bytes = base64.b64decode(frame_b64)
       nparr = np.frombuffer(img_bytes, np.uint8)
       img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
       result = DeepFace.analyze(img, actions=["emotion"], enforce_detection=False)
       dominant = result[0]["dominant_emotion"]
       return _map_to_supported(dominant)
   ```

3. **No other file needs to change** — the FastAPI endpoint and Express proxy remain identical.

---

## API Reference

### POST /predict
```json
{
  "correctness": 0,
  "responseTime": 35.5,
  "answerChanges": 3,
  "quizLevel": 2,
  "detectedExpression": "confused"
}
```
Response:
```json
{
  "learningState": "needs_hint",
  "confidence": 0.87,
  "allProbabilities": {
    "needs_hint": 0.87,
    "weak_understanding": 0.09,
    "partial_understanding": 0.03,
    "strong_understanding": 0.01
  },
  "inputFeatures": { ... }
}
```

### POST /detect-emotion
```json
{ "frame": "<base64-encoded-jpeg-string>" }
```
Response:
```json
{
  "detectedExpression": "confused",
  "supportedEmotions": ["neutral", "happy", "confused", "frustrated", "surprised"]
}
```

---

## CSV Dataset Format

| Column         | Type   | Values |
|----------------|--------|--------|
| correctness    | int    | 0 or 1 |
| responseTime   | float  | seconds |
| answerChanges  | int    | 0, 1, 2, … |
| quizLevel      | int    | 1, 2, 3 |
| faceExpression | string | neutral / happy / confused / frustrated / surprised |
| label          | string | strong_understanding / partial_understanding / weak_understanding / needs_hint |
