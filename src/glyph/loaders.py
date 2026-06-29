"""OCR orchestration: a source PDF -> a markdown ``str``.

``glyph`` runs locally as a thin orchestrator. The only loader is
:class:`MergeOcrLoader`, the one adaptive pipeline: per page it walks a ladder of
source engines, a Vision-LLM judges each candidate, and it escalates only when
confidence is low. The heavy engines are HTTP services the orchestrator spins up
on demand (see :mod:`glyph.services`):

* ``easyocr`` / ``tesseract`` -> the docling service (:mod:`glyph.docling_server`)
* ``deepseek2``               -> the DeepSeek-OCR-2 service (:mod:`glyph.ds2_server`)
* ``none``                    -> the PDF's own text layer (local, no service)

Pin a single engine by setting ``OCR_ENGINE`` to it; that just becomes a one-tier
ladder (``tiers=[[engine]]``) through the same orchestrator. Progress and
escalation are emitted as events to a :class:`~glyph.progress.ProgressReporter`.

Use :func:`make_loader` to build the loader from settings; call ``.load()`` to get
the extracted markdown.
"""

from __future__ import annotations

import time

from glyph.progress import BaseReporter, ProgressReporter
from glyph.services import ServiceError, ServiceManager

# Engines served by the docling HTTP service.
_DOCLING_ENGINES = {"easyocr", "tesseract"}


def _parse_reconcile(content: str) -> tuple[float, str]:
    """Parse the reconciler's JSON reply into ``(confidence, markdown)``.

    Defensive: strips ``` fences and falls back to the first ``{...}`` block.
    """
    import json
    import re

    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return 0.0, content
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return 0.0, content
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return confidence, str(data.get("markdown", ""))


_MERGE_SYSTEM = (
    "You reconcile OCR output into faithful Markdown. You are given a page image "
    "and one or more candidate OCR transcriptions from different engines. Using "
    "the IMAGE as ground truth, produce the most accurate, complete Markdown for "
    "the page: preserve headings, lists and tables, fix OCR errors, and keep the "
    "original language. Then rate your confidence from 0.0 to 1.0 that the result "
    "faithfully matches the page; if the candidates are poor and the image is "
    "hard to read alone, give a lower confidence so more engines are tried. "
    'Respond ONLY with a JSON object: {"confidence": <float>, "markdown": <string>}.'
)

# Optional addendum: reflow body text into continuous prose instead of mirroring
# the page's physical line breaks. Appended to the system prompt when prose mode
# is on (the default).
_MERGE_PROSE = (
    " Format body text as flowing prose: merge the hard line breaks that come only "
    "from the page layout so each paragraph is a single continuous line. Join words "
    "split across lines — drop a hyphen used to break a word, otherwise join with a "
    "single space. Remove standalone page numbers and running headers/footers that "
    "interrupt the text. Keep genuine paragraph breaks (a blank line between "
    "paragraphs) and preserve headings, lists and tables as Markdown. Do not add, "
    "drop, summarize or reorder any actual content."
)


class MergeOcrLoader:
    """Adaptive multi-engine OCR reconciled by a Vision-LLM.

    For each page, escalate through configured ``tiers`` of source engines
    (e.g. ``[["easyocr"], ["tesseract"], ["easyocr", "tesseract"]]``). A vision
    model reads the page image plus the candidate transcriptions, judges quality
    and returns the best Markdown. Escalation stops once confidence reaches
    ``min_confidence`` (or the tiers run out). Per-page engine output is cached so
    escalating never re-runs an engine.

    The orchestrator holds no ML deps: source engines are HTTP services brought up
    on demand by ``services`` and torn down at the end; ``none`` reads the PDF's
    own text layer locally. A service that won't start / is down degrades to an
    empty candidate (the reconciler still has the image and the other engines).
    """

    def __init__(
        self,
        file_path: str,
        *,
        tiers: list[list[str]],
        services: ServiceManager,
        reporter: ProgressReporter | None = None,
        pages: list[int] | None = None,
        languages: list[str] | None = None,
        force_full_page_ocr: bool = False,
        api_base: str,
        api_key: str,
        model: str,
        max_tokens: int = 8192,
        dpi: int = 144,
        min_confidence: float = 0.85,
        prose: bool = True,
        docling_url: str = "http://127.0.0.1:8002",
        deepseek2_url: str = "http://127.0.0.1:8001",
        docling_timeout: float = 180.0,
        deepseek2_timeout: float = 600.0,
    ) -> None:
        self.file_path = file_path
        self.tiers = tiers
        self.services = services
        self.reporter: ProgressReporter = reporter or BaseReporter()
        self.pages = pages  # 1-indexed PDF pages to process; None -> all
        # Reflow body text into continuous prose (strip page numbers / hard line
        # breaks) vs. mirror the page's physical layout.
        self.system_prompt = _MERGE_SYSTEM + (_MERGE_PROSE if prose else "")
        self.languages = languages or ["en"]
        self.force_full_page_ocr = force_full_page_ocr
        self.api_base = api_base
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.dpi = dpi
        self.min_confidence = min_confidence
        self.docling_url = docling_url
        self.deepseek2_url = deepseek2_url
        self.docling_timeout = docling_timeout
        self.deepseek2_timeout = deepseek2_timeout
        self.npages = 0
        self.elapsed = 0.0

    # -- HTTP to the engine services --------------------------------------
    def _post_ocr(self, base_url: str, payload: dict, *, read_timeout: float) -> str:
        import json
        import urllib.request

        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/ocr",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=read_timeout) as resp:
            return json.loads(resp.read().decode()).get("markdown", "")

    def _ocr_engine_page(self, engine: str, png_b64: str, page_text: str) -> str:
        """Run one engine for one page -> markdown (spinning its service up)."""
        if engine == "none":
            return page_text
        if engine == "deepseek2":
            self.services.ensure(
                "deepseek2", self.deepseek2_url, timeout=self.deepseek2_timeout
            )
            return self._post_ocr(
                self.deepseek2_url, {"image_b64": png_b64}, read_timeout=600
            )
        # docling engines: easyocr | tesseract
        self.services.ensure("docling", self.docling_url, timeout=self.docling_timeout)
        return self._post_ocr(
            self.docling_url,
            {
                "image_b64": png_b64,
                "engine": engine,
                "languages": self.languages,
                "force_full_page": self.force_full_page_ocr,
            },
            read_timeout=300,
        )

    def _reconcile(
        self, client, png_b64: str, candidates: dict[str, str]
    ) -> tuple[float, str]:
        blocks = "\n\n".join(
            f"### OCR engine: {eng}\n{txt}" for eng, txt in candidates.items()
        )
        user_text = (
            "Candidate OCR transcriptions:\n\n"
            f"{blocks}\n\n"
            "Return the reconciled Markdown and your confidence as JSON."
        )
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{png_b64}"},
                        },
                    ],
                },
            ],
            temperature=0.0,
            max_tokens=self.max_tokens,
        )
        return _parse_reconcile(resp.choices[0].message.content or "")

    @staticmethod
    def _page_text_layer(page) -> str:
        """The PDF's embedded text for a page (used by the ``none`` engine)."""
        try:
            textpage = page.get_textpage()
            try:
                return textpage.get_text_range()
            finally:
                textpage.close()
        except Exception:  # noqa: BLE001 — no/garbled text layer -> empty
            return ""

    def load(self, out_path: str | None = None) -> str:
        """Return the reconciled document as markdown (pages joined)."""
        import base64
        import io

        import pypdfium2 as pdfium
        from openai import OpenAI

        client = OpenAI(base_url=self.api_base, api_key=self.api_key)
        pdf = pdfium.PdfDocument(self.file_path)
        pages_md: list[str] = []
        start = time.monotonic()
        try:
            total_in_pdf = len(pdf)
            if self.pages:
                selected = [p for p in self.pages if 1 <= p <= total_in_pdf]
                dropped = [p for p in self.pages if not (1 <= p <= total_in_pdf)]
                if dropped:
                    self.reporter.on_message(
                        "warn",
                        f"ignoring pages outside 1–{total_in_pdf}: "
                        f"{', '.join(map(str, dropped))}",
                    )
            else:
                selected = list(range(1, total_in_pdf + 1))
            self.npages = len(selected)
            self.reporter.on_run_start(self.file_path, self.npages, self.tiers)
            ntiers = len(self.tiers)
            for page_no in selected:
                idx = page_no - 1
                self.reporter.on_page_start(page_no, self.npages)

                page = pdf[idx]
                bitmap = page.render(scale=self.dpi / 72.0)
                buf = io.BytesIO()
                bitmap.to_pil().save(buf, format="PNG")
                png_b64 = base64.b64encode(buf.getvalue()).decode()
                page_text = self._page_text_layer(page)

                engine_text: dict[str, str] = {}
                chosen_md = ""
                page_conf = 0.0
                page_tier = self.tiers[-1] if self.tiers else []
                for tier_idx, tier in enumerate(self.tiers):
                    for engine in tier:
                        if engine in engine_text:
                            continue
                        self.reporter.on_engine_start(page_no, engine)
                        try:
                            txt = self._ocr_engine_page(engine, png_b64, page_text)
                        except ServiceError as exc:
                            txt = ""
                            self.reporter.on_message(
                                "error", f"page {page_no}: {engine} unavailable — {exc}"
                            )
                        except Exception as exc:  # noqa: BLE001
                            txt = ""
                            self.reporter.on_message(
                                "error", f"page {page_no}: {engine} failed — {exc}"
                            )
                        engine_text[engine] = txt
                        self.reporter.on_engine_done(page_no, engine, len(txt))

                    candidates = {eng: engine_text[eng] for eng in tier}
                    confidence, chosen_md = self._reconcile(client, png_b64, candidates)
                    page_conf = confidence
                    page_tier = tier
                    accepted = confidence >= self.min_confidence
                    next_tier = (
                        self.tiers[tier_idx + 1]
                        if (not accepted and tier_idx + 1 < ntiers)
                        else None
                    )
                    self.reporter.on_reconcile(
                        page_no, tier, confidence, accepted, next_tier
                    )
                    if accepted:
                        break

                pages_md.append(chosen_md)
                self.reporter.on_page_done(page_no, page_conf, page_tier)
        finally:
            pdf.close()
            self.services.stop_all()
            self.elapsed = time.monotonic() - start
            self.reporter.on_run_done(
                len(pages_md), self.elapsed, out_path or self.file_path
            )

        return "\n\n".join(pages_md)


def make_loader(
    settings,
    file_path: str,
    services: ServiceManager | None = None,
    reporter: ProgressReporter | None = None,
    pages: list[int] | None = None,
) -> MergeOcrLoader:
    """Build the OCR orchestrator for a PDF.

    ``OCR_ENGINE=merge`` uses the full ladder; any other value pins a single
    engine (a one-tier ladder) through the same orchestrator. ``services`` /
    ``reporter`` default to a manager built from ``settings`` and a no-op reporter
    so callers (e.g. a future TUI worker) can omit them.
    """
    if services is None:
        services = ServiceManager(
            compose_file=settings.compose_file_path,
            project_name=settings.compose_project_name or None,
            poll_interval=settings.health_poll_interval,
            autostart=settings.service_autostart,
            reporter=reporter,
        )
    if settings.ocr_engine == "merge":
        tiers = settings.merge_tier_list
    else:
        tiers = [[settings.ocr_engine]]
    return MergeOcrLoader(
        file_path,
        tiers=tiers,
        services=services,
        reporter=reporter,
        pages=pages,
        languages=settings.ocr_language_list,
        force_full_page_ocr=settings.ocr_force_full_page,
        api_base=settings.merge_api_base,
        api_key=settings.merge_api_key,
        model=settings.merge_model,
        max_tokens=settings.merge_max_tokens,
        dpi=settings.merge_dpi,
        min_confidence=settings.merge_min_confidence,
        prose=settings.merge_prose,
        docling_url=settings.merge_docling_url,
        deepseek2_url=settings.merge_deepseek2_url,
        docling_timeout=settings.docling_health_timeout,
        deepseek2_timeout=settings.deepseek2_health_timeout,
    )
