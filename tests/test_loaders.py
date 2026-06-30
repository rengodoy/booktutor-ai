from glyph.config import Settings
from glyph.loaders import (
    MergeOcrLoader,
    _embed_page_images,
    _join_pages,
    _order_figures,
    _parse_reconcile,
    make_loader,
)


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


def test_join_pages_merges_lowercase_continuation():
    # Next page starts mid-sentence (lowercase) -> glue with a single space.
    out = _join_pages(["A informação pode ser", "pública ou privada."])
    assert out == "A informação pode ser pública ou privada."


def test_join_pages_dehyphenates_word_split_across_pages():
    # Page ends mid-word (trailing hyphen) -> drop the hyphen, no space.
    out = _join_pages(["O documento foi classifica-", "ção do acervo."])
    assert out == "O documento foi classificação do acervo."


def test_join_pages_keeps_break_on_new_paragraph():
    # Next page starts a fresh sentence (uppercase) -> keep the paragraph break.
    out = _join_pages(["Fim do parágrafo.", "Novo parágrafo começa aqui."])
    assert out == "Fim do parágrafo.\n\nNovo parágrafo começa aqui."


def test_join_pages_does_not_merge_into_heading():
    # A heading on the next page is structural -> never glued.
    out = _join_pages(["texto corrido anterior", "## Capítulo 2"])
    assert out == "texto corrido anterior\n\n## Capítulo 2"


def test_join_pages_does_not_merge_structural_tail():
    # A list item at the page tail stays intact even if the head is lowercase.
    out = _join_pages(["- item de lista", "continuação solta"])
    assert out == "- item de lista\n\ncontinuação solta"


def test_join_pages_merges_only_boundary_line():
    # Only the boundary paragraphs glue; the rest of each page is preserved.
    out = _join_pages(["# Título\n\nfrase que vira a", "página seguinte.\n\nOutro."])
    assert out == "# Título\n\nfrase que vira a página seguinte.\n\nOutro."


def test_join_pages_drops_empty_pages():
    out = _join_pages(["primeira", "", "Segunda."])
    assert out == "primeira\n\nSegunda."


def test_order_figures_filters_dedupes_and_sorts():
    items = [
        ("icon", 0, 0, 50, 50),  # 50x50 < 72pt -> dropped
        ("a", 100, 500, 300, 700),  # top=700, left=100
        ("a_dup", 100, 500, 300, 700),  # same bounds -> deduped
        ("b", 50, 100, 250, 300),  # top=300 -> lower on the page
        ("c", 400, 500, 600, 700),  # top=700, left=400 -> right of a
    ]
    # reading order: top-to-bottom, then left-to-right.
    assert _order_figures(items, 72.0) == ["a", "c", "b"]


def test_embed_images_fills_placeholders_in_order():
    md = "Texto.\n\n![Figura 1]()\n\nMais texto.\n\n![Figura 2]()"
    out = _embed_page_images(md, ["x.assets/p001-img1.png", "x.assets/p001-img2.png"])
    assert "![Figura 1](x.assets/p001-img1.png)" in out
    assert "![Figura 2](x.assets/p001-img2.png)" in out


def test_embed_images_drops_unbacked_placeholder():
    # No file for the placeholder -> drop the tag (no broken link), keep captions.
    out = _embed_page_images("Antes.\n\n![Figura sem arquivo]()\n\nDepois.", [])
    assert "![" not in out
    assert "Antes." in out and "Depois." in out


def test_embed_images_appends_leftover_figure():
    # The reconciler emitted no placeholder -> append the extracted figure.
    out = _embed_page_images("Só texto, sem marcação.", ["a.assets/p001-img1.png"])
    assert out.endswith("![](a.assets/p001-img1.png)")


def test_embed_images_more_images_than_placeholders_appends():
    out = _embed_page_images("![cap]()", ["d/i1.png", "d/i2.png"])
    assert "![cap](d/i1.png)" in out
    assert out.rstrip().endswith("![](d/i2.png)")


def test_embed_images_more_placeholders_than_images_drops_extra():
    out = _embed_page_images("![a]()\n\n![b]()", ["d/i1.png"])
    assert "![a](d/i1.png)" in out
    assert "![b]" not in out  # unbacked placeholder dropped (no broken link)


def test_make_loader_threads_image_settings():
    on = make_loader(_settings(), "book.pdf")
    assert on.images is True
    assert "Markdown image" in on.system_prompt
    off = make_loader(_settings(merge_images=False), "book.pdf")
    assert off.images is False
    assert "Markdown image" not in off.system_prompt


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
