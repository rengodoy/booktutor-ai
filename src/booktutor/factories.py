"""Factories that build the LLM and embeddings from :class:`Settings`.

The LLM always uses the OpenAI API standard via ``langchain_openai`` so any
OpenAI-compatible endpoint works. Embeddings can either hit an OpenAI-compatible
endpoint (``EMBEDDING_BACKEND=openai``) or run a sentence-transformers model
in-process with no separate server (``EMBEDDING_BACKEND=local``).
"""

from __future__ import annotations

from langchain_core.embeddings import Embeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from booktutor.config import Settings


def make_llm(settings: Settings) -> ChatOpenAI:
    """Build the chat model from settings."""
    return ChatOpenAI(
        model=settings.llm_model,
        base_url=settings.llm_api_base,
        api_key=settings.llm_api_key,
        temperature=settings.llm_temperature,
    )


def make_embeddings(settings: Settings) -> Embeddings:
    """Build the embeddings model from settings (openai or local backend)."""
    if settings.embedding_backend == "local":
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
        except ImportError as exc:  # pragma: no cover - depends on optional deps
            raise RuntimeError(
                "EMBEDDING_BACKEND=local requires 'langchain-huggingface' and "
                "'sentence-transformers'. Run `uv sync`."
            ) from exc
        return HuggingFaceEmbeddings(
            model_name=settings.local_embedding_model,
            encode_kwargs={"normalize_embeddings": True},
        )

    # OpenAI-compatible endpoint. check_embedding_ctx_length=False keeps
    # compatibility with servers that don't accept tokenized array input.
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        base_url=settings.resolved_embedding_api_base,
        api_key=settings.resolved_embedding_api_key,
        check_embedding_ctx_length=False,
    )
