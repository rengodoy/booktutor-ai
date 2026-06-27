from booktutor.config import Settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.llm_api_base == "https://api.openai.com/v1"
    assert s.llm_model == "gpt-4o-mini"
    assert s.embedding_model == "text-embedding-3-small"
    assert s.chunk_size == 1000
    assert s.do_ocr is True


def test_env_override(monkeypatch):
    monkeypatch.setenv("LLM_API_BASE", "http://localhost:1234/v1")
    monkeypatch.setenv("LLM_MODEL", "qwen3:latest")
    monkeypatch.setenv("CHUNK_SIZE", "512")
    s = Settings(_env_file=None)
    assert s.llm_api_base == "http://localhost:1234/v1"
    assert s.llm_model == "qwen3:latest"
    assert s.chunk_size == 512


def test_embedding_falls_back_to_llm(monkeypatch):
    monkeypatch.setenv("LLM_API_BASE", "http://localhost:1234/v1")
    monkeypatch.setenv("LLM_API_KEY", "secret")
    s = Settings(_env_file=None)
    assert s.resolved_embedding_api_base == "http://localhost:1234/v1"
    assert s.resolved_embedding_api_key == "secret"


def test_embedding_explicit_overrides_fallback(monkeypatch):
    monkeypatch.setenv("LLM_API_BASE", "http://localhost:1234/v1")
    monkeypatch.setenv("EMBEDDING_API_BASE", "http://localhost:8080/v1")
    s = Settings(_env_file=None)
    assert s.resolved_embedding_api_base == "http://localhost:8080/v1"
