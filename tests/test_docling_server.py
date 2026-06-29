from glyph.docling_server import (
    DoclingOcrRequest,
    DoclingOcrResponse,
    _TESSERACT_LANG,
)


def test_request_defaults():
    # Module-level model so FastAPI resolves it as a request body (not query).
    r = DoclingOcrRequest(image_b64="abc")
    assert r.image_b64 == "abc"
    assert r.engine == "easyocr"
    assert r.languages == ["en"]
    assert r.force_full_page is False


def test_request_overrides():
    r = DoclingOcrRequest(
        image_b64="x", engine="tesseract", languages=["pt", "en"], force_full_page=True
    )
    assert r.engine == "tesseract"
    assert r.languages == ["pt", "en"]
    assert r.force_full_page is True


def test_response():
    assert DoclingOcrResponse(markdown="# x").markdown == "# x"


def test_tesseract_lang_mapping():
    # easyocr codes (pt,en) map to tesseract codes (por,eng) in the converter.
    assert _TESSERACT_LANG["pt"] == "por"
    assert _TESSERACT_LANG["en"] == "eng"
