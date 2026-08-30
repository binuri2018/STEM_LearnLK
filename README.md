# Sri Lanka Grade 10–11 Science RAG Tutor

Syllabus-grounded Q&A: ingest **your** official PDFs (syllabus + teacher guides), retrieve chunks with **FAISS**, answer with a **strict context-only** LLM. Includes a **student web UI**, optional **OpenAI embeddings**, **Whisper** dictation, **TTS**, and **English / Sinhala** answer modes.

---

## Quick start

```powershell
cd Binuri
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # set keys / paths
```

Put PDFs under `Resource/` (see layout below), build the index, run the server, open **http://127.0.0.1:8000/**.

```powershell
python scripts\ingest.py
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

---

## Features

| Feature | Notes |
|--------|--------|
| **PDF → chunks** | PyMuPDF, ~200–400 words, metadata (grade, subject, topic, pages). |
| **Embeddings** | **`local`**: `all-MiniLM-L6-v2` (default). **`openai`**: `text-embedding-3-small` (needs key + **re-ingest**). |
| **Vector DB** | FAISS inner product on L2-normalized vectors + `index_manifest.json` so query encoder matches ingest. |
| **API** | `POST /api/ask`, `GET /api/health`, `POST /api/transcribe` (Whisper), `POST /api/tts` (MP3). Legacy `POST /ask` still works. |
| **UI** | `web/` — question box, **EN / SI / Auto** language, **voice input**, **read answer** (OpenAI or browser fallback). |
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

After changing `EMBEDDING_PROVIDER` or embedding model, **delete `data/*` and re-run `scripts/ingest.py`**.

---

## Resource folder layout

Automatic grade/subject hints (see `app/metadata_infer.py`):

- `Resource/grade10/physics/<topic>.pdf`
- `Resource/grade11/chemistry/...`
- `Resource/grade11/biology/...`

---

## API examples

```powershell
# Health
Invoke-RestMethod http://127.0.0.1:8000/api/health

# Ask (Sinhala mode example)
$body = @{ question = "ප්රකාශනය කුමක්ද?"; response_language = "si" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/ask -ContentType "application/json" -Body $body
```

---

## Module map

| Path | Role |
|------|------|
| `app/config.py` | Settings |
| `app/pdf_extract.py` | PDF text |
| `app/chunking.py` | Chunks + metadata |
| `app/metadata_infer.py` | Path/filename hints |
| `app/embeddings.py` | Local + OpenAI embeddings |
| `app/index_manifest.py` | Persist embedding backend for queries |
| `app/vector_store.py` | FAISS + JSONL |
| `app/retrieval.py` | Top-k retrieval |
| `app/llm.py` | Bilingual strict RAG prompt |
| `app/audio_services.py` | Whisper + TTS |
| `app/main.py` | FastAPI + static UI |
| `scripts/ingest.py` | Build index |
| `web/` | Student UI |

---

## Evaluation tip

After ingest, test with past-paper questions via the UI or `/api/ask`. If the model over-answers, tighten chunk sizes or increase `top_k` only with monitoring; the refusal phrases are defined in `app/llm.py`.
