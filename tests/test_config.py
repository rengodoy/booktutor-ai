from glyph.config import Settings


def test_ocr_defaults():
    s = Settings(_env_file=None)
    assert s.ocr_engine == "easyocr"
    assert s.ocr_languages == "en"
    assert s.ocr_force_full_page is False
    assert s.ocr_num_threads == 8


def test_vlm_ocr_defaults():
    s = Settings(_env_file=None)
    assert s.vlm_ocr_api_base == "http://localhost:8000/v1"
    assert s.vlm_ocr_model == "unsloth/DeepSeek-OCR"
    assert s.vlm_ocr_prompt == "Free OCR."
    assert s.vlm_ocr_max_tokens == 4096
    assert s.vlm_ocr_dpi == 144


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
