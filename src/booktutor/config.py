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

    # --- Embeddings (OpenAI-compatible) -----------------------------------
    # Fall back to the chat endpoint/key when not set explicitly.
    embedding_api_base: str | None = Field(default=None)
    embedding_api_key: str | None = Field(default=None)
    embedding_model: str = Field(default="text-embedding-3-small")

    # --- Chunking / retrieval ---------------------------------------------
    chunk_size: int = Field(default=1000)
    chunk_overlap: int = Field(default=200)
    retrieval_k: int = Field(default=5)

    # --- Storage -----------------------------------------------------------
    index_dir: Path = Field(default=Path("indexes"))

    # --- OCR (docling) -----------------------------------------------------
    do_ocr: bool = Field(default=True)
    ocr_num_threads: int = Field(default=8)

    @property
    def resolved_embedding_api_base(self) -> str:
        return self.embedding_api_base or self.llm_api_base

    @property
    def resolved_embedding_api_key(self) -> str:
        return self.embedding_api_key or self.llm_api_key
