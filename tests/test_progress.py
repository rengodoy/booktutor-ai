from glyph.loaders import MergeOcrLoader
from glyph.progress import BaseReporter, ConsoleReporter, _fmt_secs


class RecordingReporter(BaseReporter):
    """Capture every event as ``(name, kwargs)`` for assertions."""

    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def __getattribute__(self, name):
        if name.startswith("on_"):

            def record(*args, **kwargs):
                self.events.append((name, {"args": args, "kwargs": kwargs}))

            return record
        return object.__getattribute__(self, name)

    @property
    def names(self):
        return [e[0] for e in self.events]


class _DummyServices:
    """Stand-in ServiceManager: never touches docker."""

    def ensure(self, *a, **k):
        pass

    def stop_all(self):
        pass


# --- fake pypdfium2 (no PIL / native lib needed) ---------------------------
class _FakeImg:
    def save(self, buf, format):  # noqa: A002 - mirror PIL signature
        buf.write(b"\x89PNGfake")


class _FakeBitmap:
    def to_pil(self):
        return _FakeImg()


class _FakeTextpage:
    def get_text_range(self):
        return "embedded text"

    def close(self):
        pass


class _FakePage:
    def render(self, scale):
        return _FakeBitmap()

    def get_textpage(self):
        return _FakeTextpage()

    def get_objects(self):
        return []  # no embedded figures in the fake page


class _FakePdf:
    def __init__(self, path):
        self._path = path

    def __len__(self):
        return 2

    def __getitem__(self, i):
        return _FakePage()

    def close(self):
        pass


def _loader(reporter, tiers, **over):
    opts = dict(
        tiers=tiers,
        services=_DummyServices(),
        reporter=reporter,
        api_base="http://127.0.0.1:8080/v1",
        api_key="k",
        model="m",
        min_confidence=0.85,
    )
    opts.update(over)
    return MergeOcrLoader("book.pdf", **opts)


def test_fmt_secs():
    assert _fmt_secs(0) == "00:00"
    assert _fmt_secs(92) == "01:32"
    assert _fmt_secs(3723) == "1:02:03"


def test_orchestrator_emits_event_sequence(monkeypatch):
    import pypdfium2

    monkeypatch.setattr(pypdfium2, "PdfDocument", _FakePdf)
    rec = RecordingReporter()
    loader = _loader(rec, [["easyocr"]])
    monkeypatch.setattr(loader, "_ocr_engine_page", lambda e, b, t: f"ocr-{e}")
    monkeypatch.setattr(loader, "_reconcile", lambda c, b, cand, prev="": (0.99, "MD"))

    out = loader.load(out_path="out.md")

    assert out == "MD\n\nMD"  # two pages joined
    assert rec.names[0] == "on_run_start"
    assert rec.names[-1] == "on_run_done"
    assert rec.names.count("on_page_start") == 2
    assert rec.names.count("on_page_done") == 2
    assert "on_engine_start" in rec.names
    assert "on_reconcile" in rec.names
    # run_done carries the resolved output path.
    run_done = [e for n, e in rec.events if n == "on_run_done"][0]
    assert run_done["args"][2] == "out.md"


def test_orchestrator_processes_only_selected_pages(monkeypatch):
    import pypdfium2

    monkeypatch.setattr(pypdfium2, "PdfDocument", _FakePdf)  # 2-page fake
    rec = RecordingReporter()
    loader = _loader(rec, [["easyocr"]], pages=[2])
    monkeypatch.setattr(loader, "_ocr_engine_page", lambda e, b, t: "ocr")
    monkeypatch.setattr(loader, "_reconcile", lambda c, b, cand, prev="": (0.99, "P2"))

    out = loader.load()

    assert out == "P2"  # one page only
    run_start = [e for n, e in rec.events if n == "on_run_start"][0]
    assert run_start["args"][1] == 1  # total_pages == selected count
    starts = [e for n, e in rec.events if n == "on_page_start"]
    assert len(starts) == 1
    assert starts[0]["args"][0] == 2  # the real PDF page number


def test_orchestrator_warns_on_out_of_range_pages(monkeypatch):
    import pypdfium2

    monkeypatch.setattr(pypdfium2, "PdfDocument", _FakePdf)  # 2-page fake
    rec = RecordingReporter()
    loader = _loader(rec, [["easyocr"]], pages=[2, 99])
    monkeypatch.setattr(loader, "_ocr_engine_page", lambda e, b, t: "ocr")
    monkeypatch.setattr(loader, "_reconcile", lambda c, b, cand, prev="": (0.99, "P2"))

    out = loader.load()

    assert out == "P2"  # page 99 dropped, page 2 kept
    assert any(n == "on_message" and "99" in e["args"][1] for n, e in rec.events)


def test_orchestrator_escalates_on_low_confidence(monkeypatch):
    import pypdfium2

    monkeypatch.setattr(pypdfium2, "PdfDocument", _FakePdf)
    rec = RecordingReporter()
    loader = _loader(rec, [["easyocr"], ["tesseract"]])
    monkeypatch.setattr(loader, "_ocr_engine_page", lambda e, b, t: f"ocr-{e}")

    # easyocr tier -> low; tesseract tier -> high.
    def fake_reconcile(client, b64, candidates, prev=""):
        return (0.95, "GOOD") if "tesseract" in candidates else (0.50, "BAD")

    monkeypatch.setattr(loader, "_reconcile", fake_reconcile)

    loader.load()

    reconciles = [e for n, e in rec.events if n == "on_reconcile"]
    # First page: tier easyocr rejected (next_tier set), tier tesseract accepted.
    page1 = reconciles[:2]
    assert page1[0]["args"][3] is False  # accepted
    assert page1[0]["args"][4] == ["tesseract"]  # next_tier
    assert page1[1]["args"][3] is True


def test_orchestrator_degrades_on_service_error(monkeypatch):
    import pypdfium2

    from glyph.services import ServiceError

    monkeypatch.setattr(pypdfium2, "PdfDocument", _FakePdf)
    rec = RecordingReporter()
    loader = _loader(rec, [["deepseek2"]])

    def boom(engine, b64, text):
        raise ServiceError("deepseek2 down")

    monkeypatch.setattr(loader, "_ocr_engine_page", boom)
    monkeypatch.setattr(
        loader, "_reconcile", lambda c, b, cand, prev="": (0.9, "FALLBACK")
    )

    out = loader.load()

    assert out == "FALLBACK\n\nFALLBACK"  # still produced output
    assert any(n == "on_message" for n, _ in rec.events)


def test_console_reporter_plain_fallback():
    # With rich forced off, every event degrades to a plain print (no crash).
    r = ConsoleReporter()
    r._rich = False
    r.on_run_start("a.pdf", 2, [["easyocr"], ["tesseract"]])
    r.on_page_start(1, 2)
    r.on_service_starting("docling")
    r.on_service_progress("docling", None, "loading")
    r.on_service_progress("docling", 0.5, "downloading")
    r.on_service_ready("docling", 5.0)
    r.on_engine_start(1, "easyocr")
    r.on_engine_progress(1, "easyocr", None)
    r.on_engine_done(1, "easyocr", 10)
    r.on_reconcile(1, ["easyocr"], 0.6, False, ["tesseract"])
    r.on_reconcile(1, ["tesseract"], 0.9, True, None)
    r.on_page_done(1, 0.9, ["tesseract"])
    r.on_run_done(2, 12.0, "out.md")
    r.on_message("error", "boom")
