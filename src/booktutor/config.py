"""Runtime configuration loaded from environment variables / a ``.env`` file.

Everything that used to be hardcoded (model name, endpoint, key, chunking,
retrieval) now lives here. Nothing is tied to a specific provider: point the
``*_API_BASE`` variables at any OpenAI-compatible server.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from the environment or a ``.env`` file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Chat LLM (OpenAI-compatible) -------------------------------------
    llm_api_base: str = Field(
        default="https://api.openai.com/v1",
        description="Base URL of the OpenAI-compatible chat endpoint.",
    )
    llm_api_key: str = Field(
        default="not-needed",
        description="API key for the chat endpoint ('not-needed' for local servers).",
    )
    llm_model: str = Field(default="gpt-4o-mini")
    llm_temperature: float = Field(default=0.0)

    # --- Embeddings --------------------------------------------------------
    # "openai": call an OpenAI-compatible /v1/embeddings endpoint.
    # "local" : run a sentence-transformers model in-process (no server).
    embedding_backend: str = Field(default="openai")

    # Used when embedding_backend == "openai".
    # Fall back to the chat endpoint/key when not set explicitly.
    embedding_api_base: str | None = Field(default=None)
    embedding_api_key: str | None = Field(default=None)
    embedding_model: str = Field(default="text-embedding-3-small")

    # Used when embedding_backend == "local" (a sentence-transformers model id).
    local_embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2"
    )

    # --- Chunking / retrieval ---------------------------------------------
    chunk_size: int = Field(default=1000)
    chunk_overlap: int = Field(default=200)
    retrieval_k: int = Field(default=5)

    # --- Storage -----------------------------------------------------------
    index_dir: Path = Field(default=Path("indexes"))

    # --- OCR ---------------------------------------------------------------
    # Engine (manual escalation when quality is poor):
    #   "easyocr"   -> docling + EasyOCR        (local-friendly, GPU)
    #   "tesseract" -> docling + Tesseract      (Docker: lang packs installed)
    #   "vlm"       -> DeepSeek-OCR via vLLM    (Docker: best on bad scans)
    #   "none"      -> trust the PDF text layer (no OCR)
    ocr_engine: str = Field(default="easyocr")
    # Comma-separated language codes (easyocr: "pt,en"; tesseract auto-mapped).
    ocr_languages: str = Field(default="en")
    # Re-OCR the whole page, ignoring a broken/garbled embedded text layer.
    ocr_force_full_page: bool = Field(default=False)
    ocr_num_threads: int = Field(default=8)

    # --- VLM-OCR (DeepSeek-OCR served by vLLM, OpenAI-compatible vision) ----
    vlm_ocr_api_base: str = Field(default="http://localhost:8000/v1")
    vlm_ocr_api_key: str = Field(default="not-needed")
    vlm_ocr_model: str = Field(default="unsloth/DeepSeek-OCR")
    vlm_ocr_prompt: str = Field(default="Free OCR.")
    # Output tokens per page. Must leave room for image+prompt input within the
    # vLLM --max-model-len (e.g. 4096 out + image tokens < 8192).
    vlm_ocr_max_tokens: int = Field(default=4096)
    vlm_ocr_dpi: int = Field(default=144)

    @property
    def ocr_language_list(self) -> list[str]:
        return [lang.strip() for lang in self.ocr_languages.split(",") if lang.strip()]

    @property
    def resolved_embedding_api_base(self) -> str:
        return self.embedding_api_base or self.llm_api_base

    @property
    def resolved_embedding_api_key(self) -> str:
        return self.embedding_api_key or self.llm_api_key
