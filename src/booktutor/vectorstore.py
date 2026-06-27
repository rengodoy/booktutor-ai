"""FAISS vector store management, organised as named collections.

Each collection lives under ``<index_dir>/<name>/`` and can hold the chunks of
one or more books. Build once, then load from disk on later runs.
"""

from __future__ import annotations

from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from booktutor.config import Settings


def make_splitter(settings: Settings) -> RecursiveCharacterTextSplitter:
    """Text splitter configured from settings."""
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
    )


def collection_path(settings: Settings, name: str) -> Path:
    return settings.index_dir / name


def collection_exists(settings: Settings, name: str) -> bool:
    return (collection_path(settings, name) / "index.faiss").exists()


def list_collections(settings: Settings) -> list[str]:
    base = settings.index_dir
    if not base.exists():
        return []
    return sorted(
        p.name
        for p in base.iterdir()
        if p.is_dir() and (p / "index.faiss").exists()
    )


def build_collection(
    settings: Settings,
    embeddings: Embeddings,
    name: str,
    pdf_paths: list[str],
) -> FAISS:
    """Process the given PDFs into a new FAISS collection and persist it."""
    # Imported here so loaders' heavy docling import only happens on ingest.
    from booktutor.loaders import DoclingBookLoader

    splitter = make_splitter(settings)
    splits = []
    for pdf in pdf_paths:
        loader = DoclingBookLoader(
            pdf, do_ocr=settings.do_ocr, num_threads=settings.ocr_num_threads
        )
        docs = loader.load()
        splits.extend(splitter.split_documents(docs))

    if not splits:
        raise ValueError("No text could be extracted from the provided PDF(s).")

    print(f"📦 Embedding {len(splits)} chunks...")
    store = FAISS.from_documents(splits, embeddings)

    dest = collection_path(settings, name)
    dest.mkdir(parents=True, exist_ok=True)
    store.save_local(str(dest))
    print(f"💾 Saved collection '{name}' to {dest}")
    return store


def load_collection(
    settings: Settings, embeddings: Embeddings, name: str
) -> FAISS:
    if not collection_exists(settings, name):
        raise FileNotFoundError(
            f"Collection '{name}' not found under {settings.index_dir}. "
            "Ingest a book first with `booktutor ingest`."
        )
    dest = collection_path(settings, name)
    return FAISS.load_local(
        str(dest), embeddings, allow_dangerous_deserialization=True
    )


def get_or_build_collection(
    settings: Settings,
    embeddings: Embeddings,
    name: str,
    pdf_paths: list[str],
) -> FAISS:
    if collection_exists(settings, name):
        return load_collection(settings, embeddings, name)
    return build_collection(settings, embeddings, name, pdf_paths)
