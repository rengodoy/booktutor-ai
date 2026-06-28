"""OCR loaders: a source PDF -> a markdown ``str``.

The OCR engine is chosen by ``Settings.ocr_engine`` (manual escalation):

* ``easyocr`` / ``tesseract`` / ``none`` -> docling (:class:`DoclingBookLoader`)
* ``vlm`` -> DeepSeek-OCR via a vLLM vision endpoint (:class:`VlmOcrLoader`)
* ``deepseek2`` -> DeepSeek-OCR-2 in-process via transformers
  (:class:`DeepSeekOcr2Loader`)

Use :func:`make_loader` to build the right one from settings; call ``.load()``
to get the extracted markdown.
"""

from __future__ import annotations

import base64
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

        pipeline_options = PdfPipelineOptions()
        pipeline_options.accelerator_options = AcceleratorOptions(
            num_threads=self.num_threads, device=AcceleratorDevice.AUTO
        )
        pipeline_options.do_table_structure = True
        pipeline_options.table_structure_options.do_cell_matching = True

        do_ocr = self.ocr_engine != "none"
        pipeline_options.do_ocr = do_ocr
        if do_ocr:
            # force_full_page_ocr re-OCRs the whole page, ignoring a broken /
            # garbled embedded text layer (common in older scanned books).
            if self.ocr_engine == "tesseract":
                langs = [_TESSERACT_LANG.get(code, code) for code in self.ocr_languages]
                pipeline_options.ocr_options = TesseractOcrOptions(
                    lang=langs, force_full_page_ocr=self.force_full_page_ocr
                )
            else:  # easyocr
                pipeline_options.ocr_options = EasyOcrOptions(
                    lang=self.ocr_languages,
                    force_full_page_ocr=self.force_full_page_ocr,
                )

        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
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


class DeepSeekOcr2Loader:
    """OCR a PDF with DeepSeek-OCR-2 loaded **in-process** via transformers.

    No server: the model (DeepEncoder V2) runs locally with
    ``trust_remote_code``. Each page is rasterised to a temp PNG and fed to the
    model's ``infer`` method, which returns markdown.

    Needs a CUDA GPU and the model weights (downloaded once, cached by HF).
    ``attn_impl="eager"`` runs anywhere; ``"flash_attention_2"`` is faster but
    needs ``flash-attn`` installed.

    Note: the model card pins ``transformers==4.46.3``; this project resolves
    ``transformers 5.x`` (required by docling 2.10x). The remote code may not
    load on transformers 5 — validate end-to-end on your GPU; if it breaks, run
    ``deepseek2`` in a dedicated env pinned to ``transformers==4.46.3`` (or use
    the ``unsloth/DeepSeek-OCR-2`` variant, which tends to track newer releases).
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
        import torch
        from transformers import AutoModel, AutoTokenizer

        print(f"\n📚 Processing book: {self.file_path} (ocr=deepseek2:{self.model})")
        tokenizer = AutoTokenizer.from_pretrained(self.model, trust_remote_code=True)
        model = AutoModel.from_pretrained(
            self.model,
            _attn_implementation=self.attn_impl,
            trust_remote_code=True,
            use_safetensors=True,
        )
        model = model.eval().cuda().to(torch.bfloat16)

        start = time.time()
        pages_md: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            page_paths = self._render_pages_to(tmp)
            for idx, path in enumerate(page_paths, 1):
                res = model.infer(
                    tokenizer,
                    prompt=self.prompt,
                    image_file=path,
                    output_path=tmp,
                    base_size=self.base_size,
                    image_size=self.image_size,
                    crop_mode=self.crop_mode,
                    save_results=False,
                )
                pages_md.append(res if isinstance(res, str) else str(res))
                print(f"  page {idx} ✓", end="\r")

        elapsed = time.time() - start
        print(f"\n✅ Book processed in {elapsed:.2f}s ({len(pages_md)} pages)")

        return "\n\n".join(pages_md)


def make_loader(
    settings, file_path: str
) -> DoclingBookLoader | VlmOcrLoader | DeepSeekOcr2Loader:
    """Build the OCR loader for a PDF, per ``settings.ocr_engine``."""
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
