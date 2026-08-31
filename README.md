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

## Narrative Learning

Open **http://127.0.0.1:8000/narrative-learning**. This module uses its own NIE textbook index (Chroma + `nomic-embed-text`) and a persona classifier — it does not share the Voice Tutor FAISS store.

Set `LLM_PROVIDER`, `GROQ_API_KEY` or local Ollama, and `OLLAMA_EMBED_MODEL=nomic-embed-text` in `.env`. Point `NARRATIVE_VECTOR_DB` at a built `science_vector_db` folder if it is not next to the component.

Retrain the persona classifier (real Google Form + synthetic rows):

```powershell
pip install openpyxl scikit-learn pandas
python scripts\train_persona.py --survey path\to\form.xlsx --preview
python scripts\train_persona.py --survey path\to\form.xlsx
```

Then set `USE_TRAINED_CLASSIFIER=1` in `.env` and restart the server. Real survey rows are weighted 3× so ~30 answers are not drowned by the synthetic CSV.

---

## What GitHub has vs what you copy by hand

Do **not** put these on GitHub (too large, copyrighted, or private):

| Thing | Why it's off git | On another PC |
|---|---|---|
| `science_vector_db/` | Chroma RAG index (textbook embeddings) | Copy the folder, **or** rebuild (below) |
| NIE science PDFs | Copyrighted textbooks | Keep on USB / Drive, not in the repo |
| `.env` | API keys | Copy `.env.example` → `.env` and fill in |
| Ollama weights (`nomic-embed-text`, `llama3.1`) | Multi-GB local models | `ollama pull nomic-embed-text` on that PC |
| Student survey `.xlsx` | Real student answers | Keep private |

GitHub **does** include the small persona files (`persona_model.pkl`, `encoder.pkl`, ~0.7 MB) so the story-theme classifier works after clone. It does **not** include the RAG store.

### RAG database on a teammate's PC (pick one)

**A. Copy the built index (fastest, no re-embed)**  
Copy the whole `science_vector_db` folder (from this PC it lives at `C:\STEM TEXT\science_vector_db`, and LearnLK points at it with a folder junction). Place it at:

`STEM_LearnLK/backend/components/narrative_learning/science_vector_db`

Or set in `.env`:

`NARRATIVE_VECTOR_DB=C:\path\to\science_vector_db`

That PC must still run Ollama with **`nomic-embed-text`** (same embedding model used to build the index). Queries will fail if the embed model differs.

**B. Rebuild from PDFs** (only if you have the Grade 10–11 science books)

1. Install Ollama and run `ollama pull nomic-embed-text`
2. Point `ingest.py` in the STEM TEXT project at those PDFs and rebuild `science_vector_db`
3. Copy or junction that folder as in A

You do **not** need to copy `llama3.1` if `.env` uses a hosted writer (`LLM_PROVIDER=groq`). You **do** need `nomic-embed-text` for retrieval.

