from booktutor.config import Settings
from booktutor.loaders import (
    DoclingBookLoader,
    VlmOcrLoader,
    make_loader,
)


def _settings(**over) -> Settings:
    return Settings(_env_file=None, **over)


def test_make_loader_easyocr_default():
    loader = make_loader(_settings(ocr_languages="pt,en"), "book.pdf")
    assert isinstance(loader, DoclingBookLoader)
    assert loader.ocr_engine == "easyocr"
    assert loader.ocr_languages == ["pt", "en"]


def test_make_loader_tesseract():
    loader = make_loader(_settings(ocr_engine="tesseract"), "book.pdf")
    assert isinstance(loader, DoclingBookLoader)
    assert loader.ocr_engine == "tesseract"


def test_make_loader_none():
    loader = make_loader(_settings(ocr_engine="none"), "book.pdf")
    assert isinstance(loader, DoclingBookLoader)
    assert loader.ocr_engine == "none"


def test_make_loader_vlm():
    loader = make_loader(
        _settings(ocr_engine="vlm", vlm_ocr_api_base="http://vllm:8000/v1"),
        "book.pdf",
    )
    assert isinstance(loader, VlmOcrLoader)
    assert loader.api_base == "http://vllm:8000/v1"
    assert loader.model == "unsloth/DeepSeek-OCR"
    assert loader.prompt == "Free OCR."


def test_tesseract_lang_mapping():
    # easyocr codes (pt,en) map to tesseract codes (por,eng) in the converter.
    from booktutor.loaders import _TESSERACT_LANG

    assert _TESSERACT_LANG["pt"] == "por"
    assert _TESSERACT_LANG["en"] == "eng"
