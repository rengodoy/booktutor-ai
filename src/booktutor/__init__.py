"""BookTutor AI — turn any PDF book into a RAG-powered AI tutor.

Provider-agnostic: the LLM and the embeddings both talk the OpenAI API
standard, so any OpenAI-compatible endpoint works (OpenAI, Azure, vLLM,
LM Studio, Ollama, llama.cpp, ...). Configure it through environment
variables / a ``.env`` file — see :class:`booktutor.config.Settings`.
"""

from booktutor.config import Settings

__all__ = ["Settings"]
__version__ = "0.2.0"
