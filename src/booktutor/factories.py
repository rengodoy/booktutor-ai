"""Factories that build the LLM and embeddings from :class:`Settings`.

Both use the OpenAI API standard via ``langchain_openai`` so any
OpenAI-compatible endpoint works — nothing here is provider-specific.
"""

from __future__ import annotations

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


def make_embeddings(settings: Settings) -> OpenAIEmbeddings:
    """Build the embeddings model from settings.

    ``check_embedding_ctx_length=False`` keeps compatibility with
    OpenAI-compatible servers that don't accept tokenized array input.
    """
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        base_url=settings.resolved_embedding_api_base,
        api_key=settings.resolved_embedding_api_key,
        check_embedding_ctx_length=False,
    )
