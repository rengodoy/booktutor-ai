from glyph.config import Settings
from glyph.loaders import MergeOcrLoader, _parse_reconcile, make_loader


def _settings(**over) -> Settings:
    return Settings(_env_file=None, **over)


def test_make_loader_default_is_merge():
    loader = make_loader(_settings(), "book.pdf")
    assert isinstance(loader, MergeOcrLoader)
    assert loader.tiers == [
        ["easyocr"],
        ["tesseract"],
        ["easyocr", "tesseract"],
        ["easyocr", "tesseract", "deepseek2"],
    ]


def test_make_loader_pinned_easyocr():
    # A pinned engine is just a one-tier ladder through the same orchestrator.
    loader = make_loader(
        _settings(ocr_engine="easyocr", ocr_languages="pt,en"), "book.pdf"
    )
    assert isinstance(loader, MergeOcrLoader)
    assert loader.tiers == [["easyocr"]]
    assert loader.languages == ["pt", "en"]


def test_make_loader_pinned_tesseract():
    loader = make_loader(_settings(ocr_engine="tesseract"), "book.pdf")
    assert loader.tiers == [["tesseract"]]


def test_make_loader_pinned_none():
    loader = make_loader(_settings(ocr_engine="none"), "book.pdf")
    assert loader.tiers == [["none"]]


def test_make_loader_pinned_deepseek2():
    loader = make_loader(_settings(ocr_engine="deepseek2"), "book.pdf")
    assert loader.tiers == [["deepseek2"]]


def test_make_loader_merge():
    loader = make_loader(
        _settings(ocr_engine="merge", merge_model="qwen-27b", merge_min_confidence=0.9),
        "book.pdf",
    )
    assert isinstance(loader, MergeOcrLoader)
    assert loader.model == "qwen-27b"
    assert loader.min_confidence == 0.9
    assert loader.docling_url == "http://127.0.0.1:8002"
    assert loader.deepseek2_url == "http://127.0.0.1:8001"


def test_prose_mode_adds_reflow_instructions():
    # Default on: the system prompt tells the reconciler to reflow into prose.
    on = make_loader(_settings(), "book.pdf")
    assert "flowing prose" in on.system_prompt
    off = make_loader(_settings(merge_prose=False), "book.pdf")
    assert "flowing prose" not in off.system_prompt
    # Base reconciliation instructions stay in both.
    assert "reconcile OCR output" in off.system_prompt


def test_make_loader_passes_services_and_reporter():
    # Explicit services/reporter are threaded onto the loader.
    sentinel_services = object()
    sentinel_reporter = object()
    loader = make_loader(_settings(), "book.pdf", sentinel_services, sentinel_reporter)
    assert loader.services is sentinel_services
    assert loader.reporter is sentinel_reporter


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
