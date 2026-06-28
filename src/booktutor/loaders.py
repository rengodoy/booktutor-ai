"""Document loaders: source files -> LangChain ``Document`` objects.

OCR engine is chosen by ``Settings.ocr_engine`` (manual escalation):

* ``easyocr`` / ``tesseract`` / ``none`` -> docling (:class:`DoclingBookLoader`)
* ``vlm`` -> DeepSeek-OCR via a vLLM vision endpoint (:class:`VlmOcrLoader`)

Use :func:`make_loader` to build the right one from settings.
"""

from __future__ import annotations

import base64
import io
import time
from collections.abc import Iterator

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document as LCDocument

# easyocr code -> tesseract code
_TESSERACT_LANG = {
    "pt": "por",
    "en": "eng",
    "es": "spa",
    "fr": "fra",
    "de": "deu",
    "it": "ita",
}


class DoclingBookLoader(BaseLoader):
    """Load a PDF as a single markdown ``Document`` using docling + OCR."""

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
                langs = [
                    _TESSERACT_LANG.get(code, code) for code in self.ocr_languages
                ]
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

    def lazy_load(self) -> Iterator[LCDocument]:
        print(f"\n📚 Processing book: {self.file_path} (ocr={self.ocr_engine})")
        converter = self._build_converter()

        start = time.time()
        docling_doc = converter.convert(self.file_path).document
        elapsed = time.time() - start
        print(f"✅ Book processed in {elapsed:.2f}s")

        text = docling_doc.export_to_markdown()
        yield LCDocument(
            page_content=text,
            metadata={"source": self.file_path, "format": "book", "ocr": self.ocr_engine},
        )


class VlmOcrLoader(BaseLoader):
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

    def _render_pages(self) -> Iterator[bytes]:
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

    def lazy_load(self) -> Iterator[LCDocument]:
        from openai import OpenAI  # bundled via langchain-openai

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

        text = "\n\n".join(pages_md)
        yield LCDocument(
            page_content=text,
            metadata={"source": self.file_path, "format": "book", "ocr": "vlm"},
        )


class MarkdownFileLoader(BaseLoader):
    """Load a pre-extracted markdown/text file as one ``Document`` (no OCR).

    Lets a human review/fix the extracted text and feed *that* into the RAG
    instead of re-running OCR.
    """

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def lazy_load(self) -> Iterator[LCDocument]:
        with open(self.file_path, encoding="utf-8") as fh:
            text = fh.read()
        print(f"\n📄 Loading reviewed text: {self.file_path}")
        yield LCDocument(
            page_content=text,
            metadata={"source": self.file_path, "format": "markdown"},
        )


# File extensions treated as already-extracted text (skip OCR).
TEXT_SUFFIXES = {".md", ".markdown", ".txt"}


def make_loader(settings, file_path: str) -> BaseLoader:
    """Build the loader for a source file.

    Markdown/text files are loaded as-is; PDFs go through the OCR engine
    selected by ``settings.ocr_engine``.
    """
    from pathlib import Path

    if Path(file_path).suffix.lower() in TEXT_SUFFIXES:
        return MarkdownFileLoader(file_path)
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
    return DoclingBookLoader(
        file_path,
        ocr_engine=settings.ocr_engine,
        ocr_languages=settings.ocr_language_list,
        force_full_page_ocr=settings.ocr_force_full_page,
        num_threads=settings.ocr_num_threads,
    )
