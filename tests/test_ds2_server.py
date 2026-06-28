from booktutor.ds2_server import OcrRequest, OcrResponse


def test_ocr_request_defaults():
    # Module-level models so FastAPI resolves them as a request body (not query).
    r = OcrRequest(image_b64="abc")
    assert r.image_b64 == "abc"
    assert r.prompt is None
    assert r.base_size is None
    assert r.crop_mode is None


def test_ocr_request_overrides():
    r = OcrRequest(image_b64="x", prompt="P", base_size=1280, crop_mode=False)
    assert r.prompt == "P"
    assert r.base_size == 1280
    assert r.crop_mode is False


def test_ocr_response():
    assert OcrResponse(markdown="# x").markdown == "# x"
