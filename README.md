# Sri Lanka Grade 10–11 Science AI STEM Ecosystem

Syllabus-grounded Q&A: ingest **your** official PDFs (syllabus + teacher guides), retrieve chunks with **FAISS**, answer with a **strict context-only** LLM. Includes a **student web UI**, optional **OpenAI embeddings**, **Whisper** dictation, **TTS**, and **English / Sinhala** answer modes.

---

## Quick start

```powershell
cd Binuri
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # set keys / paths
```

Put PDFs under `Resource/`, build the index, run the server, open **http://127.0.0.1:8000/**.

```powershell
python scripts\ingest.py
python run.py
```
*(Or run with uvicorn: `uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000`)*

---

## Architecture & Project Structure

The project is cleanly separated into two primary directories: **`frontend/`** and **`backend/`**.

```
Binuri/
├── backend/
│   ├── main.py                     # FastAPI app, unified router mount, static file serving
│   ├── common/                     # Core backend infrastructure & RAG logic
│   │   ├── config.py               # Application settings & directory resolution
│   │   ├── embeddings.py           # Local & OpenAI embedding management
│   │   ├── vector_store.py         # FAISS vector store
│   │   ├── retrieval.py            # Top-k chunk retrieval
│   │   ├── index_manifest.py       # Persistence for embedding dimension/model
│   │   ├── chunking.py             # PDF chunking
│   │   ├── pdf_extract.py          # PyMuPDF text extractor
│   │   └── metadata_infer.py       # Grade/topic inference
│   └── components/                 # 4 separated modular components
│       ├── voice_tutor/            # Voice Tutor (Ask RAG, Whisper STT, TTS, Prompts)
│       │   ├── router.py
│       │   ├── schemas.py
│       │   ├── audio_services.py
│       │   └── llm.py
│       ├── narrative_learning/     # Narrative Learning component
│       ├── adaptive_quiz/          # Adaptive Quiz component
│       └── knowledge_maps/         # Knowledge Maps component
├── frontend/
│   ├── common/                     # Shared layout, fonts, reset, and sidebar
│   │   └── css/global.css
│   ├── home/                       # Home dashboard (Hero, Profile stats, module cards)
│   │   ├── index.html
│   │   ├── home.css
│   │   └── home.js
│   ├── voice_tutor/                # Voice Tutor module interface & audio logic
│   │   ├── index.html
│   │   ├── voice-tutor.css
│   │   └── voice-tutor.js
│   ├── narrative_learning/         # Narrative Learning page
│   ├── adaptive_quiz/              # Adaptive Quiz page
│   ├── knowledge_maps/             # Knowledge Maps page
│   └── index.html                  # Root frontend entrypoint
├── data/                           # FAISS index & metadata
├── Resource/                       # Syllabus PDFs
├── scripts/
│   └── ingest.py                   # Ingest script
└── run.py                          # Single-command launcher
```

---

## Features

| Feature | Notes |
|--------|--------|
| **PDF → chunks** | PyMuPDF, ~200–400 words, metadata (grade, subject, topic, pages). |
| **Embeddings** | **`local`**: `all-MiniLM-L6-v2` (default). **`openai`**: `text-embedding-3-small` (needs key + **re-ingest**). |
| **Vector DB** | FAISS inner product on L2-normalized vectors + `index_manifest.json` so query encoder matches ingest. |
| **API** | `POST /api/ask`, `GET /api/health`, `POST /api/transcribe` (Whisper), `POST /api/tts` (MP3). |
| **UI** | `frontend/` — question box, **EN / SI / Auto** language, **voice input**, **read answer** (OpenAI or browser fallback). |
| **Chat LLM** | OpenAI if `OPENAI_API_KEY` is set; else **Ollama** (Whisper/TTS still require OpenAI). |

---

## Environment (`.env`)

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | Chat, optional embeddings, Whisper, TTS. |
| `EMBEDDING_PROVIDER` | `local` or `openai`. |
| `EMBEDDING_MODEL` | Sentence-transformers id when `local`. |
| `OPENAI_EMBEDDING_MODEL` | e.g. `text-embedding-3-small` when `openai`. |
| `OPENAI_CHAT_MODEL` | e.g. `gpt-4o-mini`. |
| `OPENAI_TTS_MODEL` / `OPENAI_TTS_VOICE` | TTS (`alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`). |
| `OLLAMA_*` | Local chat when OpenAI key is empty. |

After changing `EMBEDDING_PROVIDER` or embedding model, **delete `data/*` and re-run `python scripts/ingest.py`**.

---

## Adaptive Quiz component

A behavior-aware, multi-level adaptive quiz: student auth, per-question timing, webcam
expression signal, ML learning-state prediction, adaptive difficulty, gamified brain-break
puzzles, a full report with a **personalised study plan + editable weekly timetable + badges**,
a **Practice mode** (turn your own PDF into an ungraded quiz), and a **teacher dashboard**
(class analytics + PDF→question generator).

**Two processes:**
1. **STEM_LearnLK app** (`python run.py`, `:8000`) — the API + the compiled React/Vite quiz UI
   (`frontend/adaptive_quiz/`), served under `/adaptive-quiz`.
2. **ML micro-service** (`ml-service/`, `:8001`) — RandomForest learning-state prediction and
   the T5 PDF→MCQ generator. Optional: if it's down, prediction falls back to an in-process
   model then a rule-based estimate; the PDF generator returns a clear error.

**Setup**

```powershell
# main app deps
pip install -r requirements.txt -r requirements-adaptive-quiz.txt
# ml-service deps (torch, transformers, sklearn, pdfplumber — large)
pip install -r ml-service\requirements.txt

# .env: MONGO_URI, JWT_SECRET, TEACHER_KEY, ML_SERVICE_URL=http://127.0.0.1:8001
python -m backend.components.adaptive_quiz.seed        # demo lesson + 9 questions

cd frontend\adaptive_quiz && npm install && npm run build && cd ..\..

# terminal 1 — ML service
cd ml-service ; python -m uvicorn main:app --host 127.0.0.1 --port 8001
# terminal 2 — main app
python run.py
```

Open **http://127.0.0.1:8000/adaptive-quiz**. Re-run `npm run build` after editing
`frontend/adaptive_quiz/src`. Teacher dashboard: `/adaptive-quiz/teacher` (enter `TEACHER_KEY`).

- Model files ship in the repo: `backend/model/best.pt` (YOLO expression) and
  `.../adaptive_quiz/models/learning_state_model.pkl` + `ml-service/models/...pkl` (RandomForest).
- If `MONGO_URI` is unset the component stays dormant; the rest of the app is unaffected.
- If the webcam / ML model / ML service is unavailable the quiz still completes.

**API** (all `/api/adaptive-quiz/`): `auth/*`, `lessons`, `assessments/*`, `responses`,
`responses/bulk`, `predict-learning-state`, `reports/*`, `study-plan/{lesson}` (GET/PUT/DEL),
`questions/generate` (teacher), `questions/practice-generate` (student), `detect-emotion`,
`status`.
