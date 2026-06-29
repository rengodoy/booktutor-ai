"""OCR loaders: a source PDF -> a markdown ``str``.

The OCR engine is chosen by ``Settings.ocr_engine`` (manual escalation):

* ``easyocr`` / ``tesseract`` / ``none`` -> docling (:class:`DoclingBookLoader`)
* ``vlm`` -> DeepSeek-OCR via a vLLM vision endpoint (:class:`VlmOcrLoader`)
* ``deepseek2`` -> DeepSeek-OCR-2 in-process via transformers
  (:class:`DeepSeekOcr2Loader`)
* ``merge`` -> adaptive multi-engine OCR reconciled by a Vision-LLM
  (:class:`MergeOcrLoader`)

Use :func:`make_loader` to build the right one from settings; call ``.load()``
to get the extracted markdown.
"""

from __future__ import annotations

import base64
import contextlib
import io
import os
import tempfile
import time

# easyocr code -> tesseract code
_TESSERACT_LANG = {
    "pt": "por",
    "en": "eng",
    "es": "spa",
    "fr": "fra",
    "de": "deu",
    "it": "ita",
}


def make_docling_converter(
    ocr_engine: str,
    *,
    ocr_languages: list[str] | None = None,
    force_full_page_ocr: bool = False,
    num_threads: int = 8,
):
    """Build a docling ``DocumentConverter`` for an OCR engine.

    ``ocr_engine`` is ``easyocr`` | ``tesseract`` | ``none``. Shared by the
    single-engine loader and the adaptive merge loader.
    """
    # Imported lazily: docling pulls in heavy ML deps (torch).
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        AcceleratorDevice,
        AcceleratorOptions,
        EasyOcrOptions,
        PdfPipelineOptions,
        TesseractOcrOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    languages = ocr_languages or ["en"]
    pipeline_options = PdfPipelineOptions()
    pipeline_options.accelerator_options = AcceleratorOptions(
        num_threads=num_threads, device=AcceleratorDevice.AUTO
    )
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options.do_cell_matching = True

    do_ocr = ocr_engine != "none"
    pipeline_options.do_ocr = do_ocr
    if do_ocr:
        # force_full_page_ocr re-OCRs the whole page, ignoring a broken /
        # garbled embedded text layer (common in older scanned books).
        if ocr_engine == "tesseract":
            langs = [_TESSERACT_LANG.get(code, code) for code in languages]
            pipeline_options.ocr_options = TesseractOcrOptions(
                lang=langs, force_full_page_ocr=force_full_page_ocr
            )
        else:  # easyocr
            pipeline_options.ocr_options = EasyOcrOptions(
                lang=languages, force_full_page_ocr=force_full_page_ocr
            )

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )


class DoclingBookLoader:
    """OCR a PDF into a single markdown string using docling."""

    def __init__(
        self,
        file_path: str,
        *,
        ocr_engine: str = "easyocr",  # "easyocr" | "tesseract" | "none"
        ocr_languages: list[str] | None = None,
        force_full_page_ocr: bool = False,
        num_threads: int = 8,
    ) -> None:
        self.file_path = file_path
        self.ocr_engine = ocr_engine
        self.ocr_languages = ocr_languages or ["en"]
        self.force_full_page_ocr = force_full_page_ocr
        self.num_threads = num_threads

    def _build_converter(self):
        return make_docling_converter(
            self.ocr_engine,
            ocr_languages=self.ocr_languages,
            force_full_page_ocr=self.force_full_page_ocr,
            num_threads=self.num_threads,
        )

    def load(self) -> str:
        """Return the OCR'd document as markdown."""
        print(f"\n📚 Processing book: {self.file_path} (ocr={self.ocr_engine})")
        converter = self._build_converter()

        start = time.time()
        docling_doc = converter.convert(self.file_path).document
        elapsed = time.time() - start
        print(f"✅ Book processed in {elapsed:.2f}s")

        return docling_doc.export_to_markdown()


class VlmOcrLoader:
    """OCR a PDF with DeepSeek-OCR served by a vLLM OpenAI-compatible endpoint.

    Each page is rasterised and sent to the vision model, which returns markdown.
    Best quality on degraded scans / complex layouts; needs the vLLM service up.
    """

    def __init__(
        self,
        file_path: str,
        *,
        api_base: str,
        api_key: str,
        model: str,
        prompt: str = "Free OCR.",
        max_tokens: int = 8192,
        dpi: int = 144,
    ) -> None:
        self.file_path = file_path
        self.api_base = api_base
        self.api_key = api_key
        self.model = model
        self.prompt = prompt
        self.max_tokens = max_tokens
        self.dpi = dpi

    def _render_pages(self):
        import pypdfium2 as pdfium  # docling dependency, already installed

        pdf = pdfium.PdfDocument(self.file_path)
        try:
            for page in pdf:
                bitmap = page.render(scale=self.dpi / 72.0)
                pil_image = bitmap.to_pil()
                buf = io.BytesIO()
                pil_image.save(buf, format="PNG")
                yield buf.getvalue()
        finally:
            pdf.close()

    def load(self) -> str:
        """Return the OCR'd document as markdown (pages joined)."""
        from openai import OpenAI

        print(
            f"\n📚 Processing book: {self.file_path} "
            f"(ocr=vlm:{self.model} @ {self.api_base})"
        )
        client = OpenAI(base_url=self.api_base, api_key=self.api_key)

        start = time.time()
        pages_md: list[str] = []
        for idx, png in enumerate(self._render_pages(), 1):
            b64 = base64.b64encode(png).decode()
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": self.prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{b64}"},
                            },
                        ],
                    }
                ],
                temperature=0.0,
                max_tokens=self.max_tokens,
            )
            pages_md.append(resp.choices[0].message.content or "")
            print(f"  page {idx} ✓", end="\r")

        elapsed = time.time() - start
        print(f"\n✅ Book processed in {elapsed:.2f}s ({len(pages_md)} pages)")

        return "\n\n".join(pages_md)


def load_deepseek2_model(model_id: str, attn_impl: str = "eager"):
    """Load DeepSeek-OCR-2 (model, tokenizer) onto CUDA via transformers.

    Shared by the per-PDF loader and the standalone OCR server so the heavy
    weights load once.
    """
    import torch
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    model = AutoModel.from_pretrained(
        model_id,
        _attn_implementation=attn_impl,
        trust_remote_code=True,
        use_safetensors=True,
    )
    model = model.eval().cuda().to(torch.bfloat16)
    return model, tokenizer


def deepseek2_ocr_image(
    model,
    tokenizer,
    image_path: str,
    *,
    prompt: str,
    base_size: int = 1024,
    image_size: int = 768,
    crop_mode: bool = True,
) -> str:
    """OCR one image file with a loaded DeepSeek-OCR-2 model -> markdown.

    ``infer`` streams to stdout and returns None; with ``save_results`` it writes
    the cleaned markdown to ``<output_path>/result.mmd`` (strips grounding/box
    refs). We read that and silence the token streamer.
    """
    with tempfile.TemporaryDirectory() as out_dir:
        with contextlib.redirect_stdout(io.StringIO()):
            model.infer(
                tokenizer,
                prompt=prompt,
                image_file=image_path,
                output_path=out_dir,
                base_size=base_size,
                image_size=image_size,
                crop_mode=crop_mode,
                save_results=True,
            )
        mmd_path = os.path.join(out_dir, "result.mmd")
        if os.path.exists(mmd_path):
            with open(mmd_path, encoding="utf-8") as fh:
                return fh.read()
    return ""


class DeepSeekOcr2Loader:
    """OCR a PDF with DeepSeek-OCR-2 loaded **in-process** via transformers.

    No server: the model (DeepEncoder V2) runs locally with
    ``trust_remote_code``. Each page is rasterised to a temp PNG and fed to the
    model's ``infer`` method, which returns markdown.

    Needs a CUDA GPU and the model weights (downloaded once, cached by HF).
    ``attn_impl="eager"`` runs anywhere; ``"flash_attention_2"`` is faster but
    needs ``flash-attn`` installed.

    The remote code needs ``transformers <4.48`` (``LlamaFlashAttention2``),
    which conflicts with docling 2.10x (transformers 5). This engine therefore
    ships in its own ``glyph[deepseek2]`` extra / image, never the docling
    one. ``infer`` streams to stdout and writes the cleaned markdown to
    ``<output_path>/result.mmd``; we read that.
    """

    def __init__(
        self,
        file_path: str,
        *,
        model: str,
        prompt: str,
        base_size: int = 1024,
        image_size: int = 768,
        crop_mode: bool = True,
        attn_impl: str = "eager",
        dpi: int = 144,
    ) -> None:
        self.file_path = file_path
        self.model = model
        self.prompt = prompt
        self.base_size = base_size
        self.image_size = image_size
        self.crop_mode = crop_mode
        self.attn_impl = attn_impl
        self.dpi = dpi

    def _render_pages_to(self, out_dir: str) -> list[str]:
        import pypdfium2 as pdfium  # docling dependency, already installed

        paths: list[str] = []
        pdf = pdfium.PdfDocument(self.file_path)
        try:
            for i, page in enumerate(pdf):
                bitmap = page.render(scale=self.dpi / 72.0)
                pil_image = bitmap.to_pil()
                path = os.path.join(out_dir, f"page_{i:04d}.png")
                pil_image.save(path, format="PNG")
                paths.append(path)
        finally:
            pdf.close()
        return paths

    def load(self) -> str:
        """Return the OCR'd document as markdown (pages joined)."""
        print(f"\n📚 Processing book: {self.file_path} (ocr=deepseek2:{self.model})")
        model, tokenizer = load_deepseek2_model(self.model, self.attn_impl)

        start = time.time()
        pages_md: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            page_paths = self._render_pages_to(tmp)
            for idx, path in enumerate(page_paths, 1):
                page_md = deepseek2_ocr_image(
                    model,
                    tokenizer,
                    path,
                    prompt=self.prompt,
                    base_size=self.base_size,
                    image_size=self.image_size,
                    crop_mode=self.crop_mode,
                )
                pages_md.append(page_md)
                print(f"  page {idx} ✓", end="\r")

        elapsed = time.time() - start
        print(f"\n✅ Book processed in {elapsed:.2f}s ({len(pages_md)} pages)")

        return "\n\n".join(pages_md)


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


class MergeOcrLoader:
    """Adaptive multi-engine OCR reconciled by a Vision-LLM.

    For each page, escalate through configured ``tiers`` of source engines
    (e.g. ``[["easyocr"], ["tesseract"], ["easyocr", "tesseract"]]``). A vision
    model reads the page image plus the candidate transcriptions, judges quality
    and returns the best Markdown. Escalation stops once confidence reaches
    ``min_confidence`` (or the tiers run out). Per-page engine output is cached so
    escalating never re-runs an engine.

    Runs in the docling image (docling engines + an OpenAI-compatible vision
    endpoint). The ``deepseek2`` source engine can't run here (transformers
    conflict), so it's called over HTTP at ``deepseek2_url`` — the standalone
    DeepSeek-OCR-2 server (see ds2_server / Dockerfile.deepseek2). If that
    service is down, the deepseek2 candidate is skipped.
    """

    def __init__(
        self,
        file_path: str,
        *,
        tiers: list[list[str]],
        languages: list[str] | None = None,
        force_full_page_ocr: bool = False,
        num_threads: int = 8,
        api_base: str,
        api_key: str,
        model: str,
        max_tokens: int = 8192,
        dpi: int = 144,
        min_confidence: float = 0.85,
        deepseek2_url: str = "http://127.0.0.1:8001",
    ) -> None:
        self.file_path = file_path
        self.tiers = tiers
        self.languages = languages or ["en"]
        self.force_full_page_ocr = force_full_page_ocr
        self.num_threads = num_threads
        self.api_base = api_base
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.dpi = dpi
        self.min_confidence = min_confidence
        self.deepseek2_url = deepseek2_url

    def _converter_for(self, engine: str, cache: dict):
        if engine not in cache:
            cache[engine] = make_docling_converter(
                engine,
                ocr_languages=self.languages,
                force_full_page_ocr=self.force_full_page_ocr,
                num_threads=self.num_threads,
            )
        return cache[engine]

    def _ocr_page(self, converter, page_no: int) -> str:
        # page_range is 1-indexed and inclusive.
        result = converter.convert(self.file_path, page_range=(page_no, page_no))
        return result.document.export_to_markdown()

    def _ocr_deepseek2(self, png_b64: str) -> str:
        # Call the standalone DeepSeek-OCR-2 HTTP server (separate venv/image).
        import json
        import urllib.request

        req = urllib.request.Request(
            f"{self.deepseek2_url.rstrip('/')}/ocr",
            data=json.dumps({"image_b64": png_b64}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.loads(resp.read().decode()).get("markdown", "")

    def _ocr_engine_page(
        self, engine: str, converters: dict, page_no: int, png_b64: str
    ) -> str:
        if engine == "deepseek2":
            return self._ocr_deepseek2(png_b64)
        converter = self._converter_for(engine, converters)
        return self._ocr_page(converter, page_no)

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
                {"role": "system", "content": _MERGE_SYSTEM},
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

    def load(self) -> str:
        """Return the reconciled document as markdown (pages joined)."""
        import pypdfium2 as pdfium
        from openai import OpenAI

        print(
            f"\n📚 Processing book: {self.file_path} "
            f"(ocr=merge:{self.model}, tiers={self.tiers})"
        )
        client = OpenAI(base_url=self.api_base, api_key=self.api_key)
        converters: dict = {}

        start = time.time()
        pages_md: list[str] = []
        pdf = pdfium.PdfDocument(self.file_path)
        try:
            npages = len(pdf)
            for idx in range(npages):
                bitmap = pdf[idx].render(scale=self.dpi / 72.0)
                buf = io.BytesIO()
                bitmap.to_pil().save(buf, format="PNG")
                png_b64 = base64.b64encode(buf.getvalue()).decode()

                page_no = idx + 1
                engine_text: dict[str, str] = {}
                chosen_md = ""
                used_tier: list[str] = []
                for tier in self.tiers:
                    for engine in tier:
                        if engine not in engine_text:
                            # A failed engine (tesseract without tessdata, the
                            # deepseek2 service being down, ...) becomes an empty
                            # candidate; the reconciler still has the image and
                            # the other engines.
                            try:
                                engine_text[engine] = self._ocr_engine_page(
                                    engine, converters, page_no, png_b64
                                )
                            except Exception as exc:  # noqa: BLE001
                                engine_text[engine] = ""
                                print(f"\n  [engine {engine} failed: {exc}]")
                    candidates = {eng: engine_text[eng] for eng in tier}
                    confidence, chosen_md = self._reconcile(client, png_b64, candidates)
                    used_tier = tier
                    if confidence >= self.min_confidence:
                        break
                pages_md.append(chosen_md)
                print(
                    f"  page {page_no}/{npages} ✓ (tier={','.join(used_tier)})",
                    end="\r",
                )
        finally:
            pdf.close()

        elapsed = time.time() - start
        print(f"\n✅ Book processed in {elapsed:.2f}s ({len(pages_md)} pages)")

        return "\n\n".join(pages_md)


def make_loader(
    settings, file_path: str
) -> DoclingBookLoader | VlmOcrLoader | DeepSeekOcr2Loader | MergeOcrLoader:
    """Build the OCR loader for a PDF, per ``settings.ocr_engine``."""
    if settings.ocr_engine == "merge":
        return MergeOcrLoader(
            file_path,
            tiers=settings.merge_tier_list,
            languages=settings.ocr_language_list,
            force_full_page_ocr=settings.ocr_force_full_page,
            num_threads=settings.ocr_num_threads,
            api_base=settings.merge_api_base,
            api_key=settings.merge_api_key,
            model=settings.merge_model,
            max_tokens=settings.merge_max_tokens,
            dpi=settings.merge_dpi,
            min_confidence=settings.merge_min_confidence,
            deepseek2_url=settings.merge_deepseek2_url,
        )
    if settings.ocr_engine == "vlm":
        return VlmOcrLoader(
            file_path,
            api_base=settings.vlm_ocr_api_base,
            api_key=settings.vlm_ocr_api_key,
            model=settings.vlm_ocr_model,
            prompt=settings.vlm_ocr_prompt,
            max_tokens=settings.vlm_ocr_max_tokens,
            dpi=settings.vlm_ocr_dpi,
        )
    if settings.ocr_engine == "deepseek2":
        return DeepSeekOcr2Loader(
            file_path,
            model=settings.ds2_model,
            prompt=settings.ds2_prompt,
            base_size=settings.ds2_base_size,
            image_size=settings.ds2_image_size,
            crop_mode=settings.ds2_crop_mode,
            attn_impl=settings.ds2_attn_impl,
            dpi=settings.ds2_dpi,
        )
    return DoclingBookLoader(
        file_path,
        ocr_engine=settings.ocr_engine,
        ocr_languages=settings.ocr_language_list,
        force_full_page_ocr=settings.ocr_force_full_page,
        num_threads=settings.ocr_num_threads,
    )
