from pathlib import Path

from langchain_core.documents import Document

from booktutor.config import Settings
from booktutor.vectorstore import (
    collection_exists,
    collection_path,
    list_collections,
    make_splitter,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(index_dir=tmp_path, _env_file=None)


def test_collection_path(tmp_path):
    s = _settings(tmp_path)
    assert collection_path(s, "physics") == tmp_path / "physics"


def test_list_collections_empty(tmp_path):
    s = _settings(tmp_path)
    assert list_collections(s) == []


def test_list_collections_detects_built(tmp_path):
    s = _settings(tmp_path)
    for name in ("alpha", "beta"):
        d = tmp_path / name
        d.mkdir()
        (d / "index.faiss").write_bytes(b"")
    # A bare dir without index.faiss must not count.
    (tmp_path / "incomplete").mkdir()
    assert list_collections(s) == ["alpha", "beta"]
    assert collection_exists(s, "alpha")
    assert not collection_exists(s, "incomplete")


def test_splitter_chunks_long_text(tmp_path):
    s = _settings(tmp_path)
    s = s.model_copy(update={"chunk_size": 100, "chunk_overlap": 20})
    splitter = make_splitter(s)
    doc = Document(page_content="palavra " * 500)
    chunks = splitter.split_documents([doc])
    assert len(chunks) > 1
    assert all(len(c.page_content) <= 100 for c in chunks)
