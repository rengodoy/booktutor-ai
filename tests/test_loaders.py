from booktutor.config import Settings
from booktutor.loaders import (
    DeepSeekOcr2Loader,
    DoclingBookLoader,
    MergeOcrLoader,
    VlmOcrLoader,
    _parse_reconcile,
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


def test_make_loader_deepseek2():
    loader = make_loader(
        _settings(ocr_engine="deepseek2", ds2_image_size=640),
        "book.pdf",
    )
    assert isinstance(loader, DeepSeekOcr2Loader)
    assert loader.model == "deepseek-ai/DeepSeek-OCR-2"
    assert loader.image_size == 640
    assert loader.crop_mode is True
    assert loader.attn_impl == "eager"
    assert "<|grounding|>" in loader.prompt


def test_make_loader_merge():
    loader = make_loader(
        _settings(ocr_engine="merge", merge_model="qwen-27b", merge_min_confidence=0.9),
        "book.pdf",
    )
    assert isinstance(loader, MergeOcrLoader)
    assert loader.model == "qwen-27b"
    assert loader.min_confidence == 0.9
    assert loader.tiers == [["easyocr"], ["tesseract"], ["easyocr", "tesseract"]]


def test_merge_tier_list_parsing():
    s = _settings(merge_tiers="easyocr ; tesseract , easyocr ; deepseek2")
    assert s.merge_tier_list == [["easyocr"], ["tesseract", "easyocr"], ["deepseek2"]]


def test_parse_reconcile_plain_json():
    conf, md = _parse_reconcile('{"confidence": 0.92, "markdown": "# Title"}')
    assert conf == 0.92
    assert md == "# Title"


def test_parse_reconcile_fenced_json():
    conf, md = _parse_reconcile('```json\n{"confidence": 0.5, "markdown": "x"}\n```')
    assert conf == 0.5
    assert md == "x"


def test_parse_reconcile_garbage_falls_back():
    conf, md = _parse_reconcile("not json at all")
    assert conf == 0.0
    assert md == "not json at all"


def test_tesseract_lang_mapping():
    # easyocr codes (pt,en) map to tesseract codes (por,eng) in the converter.
    from booktutor.loaders import _TESSERACT_LANG

    assert _TESSERACT_LANG["pt"] == "por"
    assert _TESSERACT_LANG["en"] == "eng"
