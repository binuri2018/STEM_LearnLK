"""
Application settings loaded from environment / .env.
"""
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Project root = parent of `backend/`
    project_root: Path = Path(__file__).resolve().parent.parent.parent
    resource_dir: Path = Path("Resource")
    data_dir: Path = Path("data")
    frontend_dir: Path = Path("frontend")

    # Ingest-time: "local" = sentence-transformers, "openai" = OpenAI embeddings (needs API key)
    embedding_provider: Literal["local", "openai"] = "local"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    # If HF/model HTTPS fails with CERTIFICATE_VERIFY_FAILED, set USE_CERTIFI_SSL=1 (needs certifi).
    use_certifi_ssl: bool = False
    # Dev-only: disables TLS verification for HTTPS (fixes some corporate/broken CA setups). Not for production.
    binuri_disable_ssl_verify: bool = False
    openai_embedding_model: str = "text-embedding-3-small"
    top_k: int = 5

    chunk_min_words: int = 200
    chunk_max_words: int = 400

    # OpenAI (preferred when key is set)
    openai_api_key: str | None = None
    openai_chat_model: str = "gpt-4o-mini"
    openai_tts_model: str = "tts-1"
    openai_tts_voice: str = "nova"

    # Ollama fallback
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "mistral"
    # First local inference after pull/start can exceed 120s while the model loads into RAM.
    ollama_timeout_seconds: float = 600.0

    faiss_index_name: str = "science_index.faiss"
    metadata_name: str = "science_metadata.jsonl"
    index_manifest_name: str = "index_manifest.json"
    image_faiss_index_name: str = "image_index.faiss"
    image_metadata_name: str = "image_metadata.jsonl"

    def resolved_resource_dir(self) -> Path:
        p = self.resource_dir
        return p if p.is_absolute() else (self.project_root / p)

    def resolved_data_dir(self) -> Path:
        p = self.data_dir
        return p if p.is_absolute() else (self.project_root / p)

    def resolved_frontend_dir(self) -> Path:
        p = self.frontend_dir
        return p if p.is_absolute() else (self.project_root / p)


settings = Settings()
