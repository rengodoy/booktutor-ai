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

import re
import time

from glyph.progress import BaseReporter, ProgressReporter
from glyph.services import ServiceError, ServiceManager

# Engines served by the docling HTTP service.
_DOCLING_ENGINES = {"easyocr", "tesseract"}

# Markdown lines that must not be glued to a neighbour across a page break.
_STRUCT_PREFIXES = ("#", ">", "|", "```", "![")
_LIST_RE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s)")


def _structural_line(line: str) -> bool:
    """True for a heading / list item / table row / code fence / blank line."""
    s = line.strip()
    if not s:
        return True
    if s.startswith(_STRUCT_PREFIXES):
        return True
    return bool(_LIST_RE.match(line))


def _continues_sentence(head: str) -> bool:
    """The first line of a page continues the previous page's sentence.

    Its first letter is lowercase — a fresh paragraph/sentence would start
    uppercase, so a lowercase start is almost always a mid-sentence carry-over.
    """
    m = re.search(r"[^\W\d_]", head)
    return bool(m) and m.group(0).islower()


def _is_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.count("|") >= 2


def _is_separator_row(line: str) -> bool:
    """A Markdown table separator like ``| --- | :--: |``."""
    s = line.strip()
    return bool(re.fullmatch(r"\|[\s:|-]+\|", s)) and "-" in s


def _table_cols(line: str) -> int:
    return len(line.strip().strip("|").split("|"))


def _trailing_table_start(lines: list[str]) -> int:
    """Index where the page's trailing run of table rows starts (``len`` if none)."""
    i = len(lines)
    while i > 0 and _is_table_row(lines[i - 1]):
        i -= 1
    return i


def _leading_table_end(lines: list[str]) -> int:
    """Index just past the page's leading run of table rows (``0`` if none)."""
    j = 0
    while j < len(lines) and _is_table_row(lines[j]):
        j += 1
    return j


def _stitch_tables(prev_lines: list[str], cur_lines: list[str]) -> list[str] | None:
    """Merge a table split across a page break, or ``None`` if there isn't one.

    The previous page must end with table rows and the current page must begin
    with table rows of the same column count. The continuation's repeated header
    (header + separator) — or a stray leading separator — is dropped, then its
    body rows are appended to the previous table. Any non-table remainder of the
    current page is kept after a blank line.
    """
    ts = _trailing_table_start(prev_lines)
    te = _leading_table_end(cur_lines)
    prev_tbl, cur_tbl = prev_lines[ts:], cur_lines[:te]
    if not prev_tbl or not cur_tbl:
        return None
    if _table_cols(prev_tbl[-1]) != _table_cols(cur_tbl[0]):
        return None
    cont = cur_tbl
    if len(cont) >= 2 and _is_separator_row(cont[1]):
        cont = cont[2:]  # drop a repeated "header + separator"
    elif cont and _is_separator_row(cont[0]):
        cont = cont[1:]  # drop a stray leading separator
    merged = prev_lines[:ts] + prev_tbl + cont
    rest = cur_lines[te:]
    while rest and not rest[0].strip():
        rest = rest[1:]  # drop blank lines between the table and the rest
    if rest:
        merged += [""] + rest
    return merged


def _join_pages(pages: list[str], *, prose: bool = True, tables: bool = True) -> str:
    """Join page markdowns, stitching content split across a page break.

    Per boundary, in order: if ``tables`` and both sides are a table with matching
    columns, the table is stitched into one (repeated header dropped). Else if
    ``prose`` and the page ends mid-word (trailing ``-``) or the next starts
    mid-sentence (lowercase first letter) and neither side is structural, the two
    paragraphs are glued into one line. Otherwise the usual blank-line paragraph
    break is kept. Empty pages are dropped.
    """
    out = ""
    for page in pages:
        page = page.strip("\n")
        if not page.strip():
            continue
        if not out:
            out = page
            continue
        prev = out.rstrip()
        prev_lines = prev.split("\n")
        cur_lines = page.split("\n")
        stitched = _stitch_tables(prev_lines, cur_lines) if tables else None
        if stitched is not None:
            out = "\n".join(stitched)
            continue
        tail, head = prev_lines[-1], cur_lines[0]
        if (
            prose
            and not _structural_line(tail)
            and not _structural_line(head)
            and (tail.rstrip().endswith("-") or _continues_sentence(head))
        ):
            tail_text, head_text = tail.rstrip(), head.lstrip()
            if tail_text.endswith("-"):
                glued = tail_text[:-1] + head_text  # de-hyphenate a split word
            else:
                glued = tail_text + " " + head_text
            out = "\n".join(prev_lines[:-1] + [glued] + cur_lines[1:])
        else:
            out = prev + "\n\n" + page
    return out


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

# Optional addendum: ask the reconciler to mark each figure with a Markdown image
# placeholder (empty URL) at its position. The orchestrator extracts the embedded
# images from the PDF and fills these URLs in afterwards (see ``_embed_page_images``).
_MERGE_IMAGES = (
    " For each figure, photo, screenshot, chart or diagram on the page, emit a "
    "Markdown image at its position with an EMPTY url and the figure's caption as "
    "alt text, e.g. ![Figura 6 - Sistema e-SIC](). Do not invent a url — it is "
    "filled in afterwards. Still transcribe any caption and source lines (e.g. "
    "'Figura 6 - ...', 'Fonte: ...') as normal text around the image."
)

# Optional addendum: the reconciler is handed the tail of the previous page so it
# can continue a structure that spans the page break. Appended when prose or table
# stitching is on.
_MERGE_CONTINUATION = (
    " You may be given the tail of the PREVIOUS page purely as context. Do not "
    "re-transcribe it — transcribe only the current page (the image). If the "
    "current page continues a table, list or sentence from the previous page, "
    "continue it seamlessly with the SAME structure. For a table that continues, "
    "reuse the exact same columns; repeating the header row is fine (the tool "
    "merges a table split across pages)."
)

# Markdown image tags: ``![alt](url)``. ``_EMPTY_IMG_RE`` is one we couldn't back
# with an extracted file (left with an empty url) -> dropped so there's no broken
# link, keeping the surrounding caption text.
_IMG_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<url>[^)]*)\)")
_EMPTY_IMG_RE = re.compile(r"!\[[^\]]*\]\(\s*\)")


def _order_figures(items: list[tuple], min_pt: float) -> list:
    """Filter / dedupe / order embedded images into figures, reading order.

    ``items`` is ``[(ref, left, bottom, right, top), ...]`` with bounds in PDF
    points. Drops anything smaller than ``min_pt`` on either side (icons, bullets,
    header strips), dedupes by bounding box (pdfium can repeat an object), and
    sorts top-to-bottom then left-to-right. Returns the kept ``ref`` values.
    """
    seen: set[tuple] = set()
    kept: list[tuple] = []
    for ref, left, bottom, right, top in items:
        if (right - left) < min_pt or (top - bottom) < min_pt:
            continue
        key = (round(left, 1), round(bottom, 1), round(right, 1), round(top, 1))
        if key in seen:
            continue
        seen.add(key)
        kept.append((ref, left, bottom, right, top))
    kept.sort(key=lambda x: (-x[4], x[1]))  # top desc, then left asc
    return [x[0] for x in kept]


def _embed_page_images(md: str, rel_paths: list[str]) -> str:
    """Back the reconciler's image placeholders with extracted figure files.

    Fills each ``![alt]()`` url with the next extracted path (reading order),
    drops any placeholder we couldn't back with a file, and appends any leftover
    extracted images the reconciler didn't place. Collapses blank-line runs.
    """
    paths = iter(rel_paths)

    def _fill(m: re.Match) -> str:
        try:
            path = next(paths)
        except StopIteration:
            return m.group(0)  # no file left -> stripped by _EMPTY_IMG_RE below
        return f"![{m.group('alt')}]({path})"

    out = _IMG_RE.sub(_fill, md)
    leftover = list(paths)
    out = _EMPTY_IMG_RE.sub("", out)  # drop placeholders with no backing file
    if leftover:
        out = out.rstrip() + "\n\n" + "\n\n".join(f"![]({p})" for p in leftover)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


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
        images: bool = True,
        min_figure_pt: float = 72.0,
        tables: bool = True,
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
        # breaks) vs. mirror the page's physical layout. When on, also stitch a
        # sentence/word split across a page break (see ``_join_pages``).
        self.prose = prose
        # Extract embedded figures as files and back the reconciler's image
        # placeholders with real links (see ``_extract_page_images``).
        self.images = images
        self.min_figure_pt = min_figure_pt
        # Stitch a table split across a page break, and feed the previous page's
        # tail to the reconciler so it continues spanning structures (see
        # ``_stitch_tables`` / ``_MERGE_CONTINUATION``).
        self.tables = tables
        self.system_prompt = (
            _MERGE_SYSTEM
            + (_MERGE_PROSE if prose else "")
            + (_MERGE_IMAGES if images else "")
            + (_MERGE_CONTINUATION if (prose or tables) else "")
        )
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
        self,
        client,
        png_b64: str,
        candidates: dict[str, str],
        prev_tail: str = "",
    ) -> tuple[float, str]:
        blocks = "\n\n".join(
            f"### OCR engine: {eng}\n{txt}" for eng, txt in candidates.items()
        )
        context = ""
        if prev_tail.strip():
            context = (
                "Tail of the PREVIOUS page (context only — do NOT re-transcribe; "
                "use it to continue any table/list/sentence that spans the page "
                f"break):\n\n{prev_tail.strip()}\n\n---\n\n"
            )
        user_text = (
            f"{context}"
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

    def _extract_page_images(
        self, page, page_no: int, assets_dir, assets_rel: str
    ) -> list[str]:
        """Save the page's embedded figures as PNGs -> their markdown-relative paths.

        Enumerates image objects, keeps the figure-sized ones (``_order_figures``),
        renders each to a PNG under ``assets_dir`` and returns the paths to use in
        the markdown (``assets_rel/p<NN>-img<MM>.png``), in reading order.
        """
        import pypdfium2.raw as pdfium_raw

        items: list[tuple] = []
        for obj in page.get_objects():
            if obj.type != pdfium_raw.FPDF_PAGEOBJ_IMAGE:
                continue
            try:
                left, bottom, right, top = obj.get_bounds()
            except Exception:  # noqa: BLE001 — skip an object we can't place
                continue
            items.append((obj, left, bottom, right, top))

        rel_paths: list[str] = []
        for n, obj in enumerate(_order_figures(items, self.min_figure_pt), 1):
            try:
                image = obj.get_bitmap(render=True).to_pil()
                if image.mode == "RGBA" and image.getchannel("A").getextrema() == (
                    255,
                    255,
                ):
                    image = image.convert("RGB")  # opaque -> drop alpha, smaller file
                assets_dir.mkdir(parents=True, exist_ok=True)
                name = f"p{page_no:03d}-img{n}.png"
                image.save(assets_dir / name, format="PNG", optimize=True)
                rel_paths.append(f"{assets_rel}/{name}")
            except Exception as exc:  # noqa: BLE001 — one bad figure shouldn't fail the page
                self.reporter.on_message(
                    "warn", f"page {page_no}: could not extract a figure — {exc}"
                )
        return rel_paths

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
        from pathlib import Path

        import pypdfium2 as pdfium
        from openai import OpenAI

        client = OpenAI(base_url=self.api_base, api_key=self.api_key)
        pdf = pdfium.PdfDocument(self.file_path)
        pages_md: list[str] = []
        # Figures are written to a sibling "<output stem>.assets/" dir so the
        # markdown links resolve next to the .md file.
        out_basis = Path(out_path) if out_path else Path(self.file_path)
        assets_rel = f"{out_basis.stem}.assets"
        assets_dir = out_basis.parent / assets_rel
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
            want_context = self.tables or self.prose
            prev_tail = ""  # tail of the previous page's reconciled markdown
            prev_page_no: int | None = None
            for page_no in selected:
                idx = page_no - 1
                self.reporter.on_page_start(page_no, self.npages)
                # Only feed continuation context between physically adjacent pages
                # (a non-contiguous --pages selection must not bleed across gaps).
                adjacent = prev_page_no is not None and page_no == prev_page_no + 1
                tail_ctx = prev_tail if adjacent else ""

                page = pdf[idx]
                bitmap = page.render(scale=self.dpi / 72.0)
                buf = io.BytesIO()
                bitmap.to_pil().save(buf, format="PNG")
                png_b64 = base64.b64encode(buf.getvalue()).decode()
                page_text = self._page_text_layer(page)
                page_images = (
                    self._extract_page_images(page, page_no, assets_dir, assets_rel)
                    if self.images
                    else []
                )

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
                    confidence, chosen_md = self._reconcile(
                        client, png_b64, candidates, tail_ctx
                    )
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

                # Capture the tail BEFORE image embed (no link junk in the context).
                prev_tail = chosen_md[-1200:] if want_context else ""
                prev_page_no = page_no
                if self.images:
                    chosen_md = _embed_page_images(chosen_md, page_images)
                pages_md.append(chosen_md)
                self.reporter.on_page_done(page_no, page_conf, page_tier)
        finally:
            pdf.close()
            self.services.stop_all()
            self.elapsed = time.monotonic() - start
            self.reporter.on_run_done(
                len(pages_md), self.elapsed, out_path or self.file_path
            )

        if self.prose or self.tables:
            return _join_pages(pages_md, prose=self.prose, tables=self.tables)
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
        images=settings.merge_images,
        min_figure_pt=settings.merge_min_figure_pt,
        tables=settings.merge_tables,
        docling_url=settings.merge_docling_url,
        deepseek2_url=settings.merge_deepseek2_url,
        docling_timeout=settings.docling_health_timeout,
        deepseek2_timeout=settings.deepseek2_health_timeout,
    )
