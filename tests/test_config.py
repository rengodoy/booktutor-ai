from glyph.config import Settings


def test_ocr_defaults():
    s = Settings(_env_file=None)
    assert s.ocr_engine == "merge"
    assert s.ocr_languages == "en"
    assert s.ocr_force_full_page is False
    assert s.ocr_num_threads == 8


def test_env_override(monkeypatch):
    monkeypatch.setenv("OCR_ENGINE", "tesseract")
    monkeypatch.setenv("OCR_NUM_THREADS", "4")
    s = Settings(_env_file=None)
    assert s.ocr_engine == "tesseract"
    assert s.ocr_num_threads == 4


def test_ocr_language_list(monkeypatch):
    monkeypatch.setenv("OCR_LANGUAGES", " pt , en ")
    s = Settings(_env_file=None)
    assert s.ocr_language_list == ["pt", "en"]


def test_service_defaults():
    s = Settings(_env_file=None)
    assert s.docling_server_port == 8002
    assert s.merge_docling_url == "http://127.0.0.1:8002"
    # glyph runs locally now -> the deepseek2 service is on a published host port.
    assert s.merge_deepseek2_url == "http://127.0.0.1:8001"
    assert s.compose_file == "docker-compose.yaml"
    assert s.compose_project_name == ""
    assert s.service_autostart is True
    assert s.service_stop_on_exit is True
    assert s.docling_health_timeout == 180.0
    assert s.deepseek2_health_timeout == 600.0
    assert s.health_poll_interval == 2.0


def test_compose_file_path_is_absolute():
    import os

    s = Settings(_env_file=None)
    assert os.path.isabs(s.compose_file_path)
    assert s.compose_file_path.endswith("docker-compose.yaml")


def test_compose_file_path_env_override(monkeypatch, tmp_path):
    target = tmp_path / "custom-compose.yaml"
    target.write_text("services: {}\n")
    monkeypatch.setenv("GLYPH_COMPOSE_FILE", str(target))
    s = Settings(_env_file=None)
    assert s.compose_file_path == str(target.resolve())
