"""Document loaders that turn source files into LangChain ``Document`` objects.

Uses `docling` to convert PDFs (including scanned ones, via OCR) to markdown.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document as LCDocument


class DoclingBookLoader(BaseLoader):
    """Load a PDF as a single markdown ``Document`` using docling."""

    def __init__(
        self,
        file_path: str,
        *,
        do_ocr: bool = True,
        num_threads: int = 8,
    ) -> None:
        self.file_path = file_path
        self.do_ocr = do_ocr
        self.num_threads = num_threads

    def _build_converter(self):
        # Imported lazily: docling pulls in heavy ML deps (torch), so importing
        # it at module load would slow down every CLI invocation and the tests.
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            AcceleratorDevice,
            AcceleratorOptions,
            PdfPipelineOptions,
        )
        from docling.document_converter import DocumentConverter, PdfFormatOption

        pipeline_options = PdfPipelineOptions()
        pipeline_options.accelerator_options = AcceleratorOptions(
            num_threads=self.num_threads, device=AcceleratorDevice.AUTO
        )
        pipeline_options.do_ocr = self.do_ocr
        pipeline_options.do_table_structure = True
        pipeline_options.table_structure_options.do_cell_matching = True

        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )

    def lazy_load(self) -> Iterator[LCDocument]:
        print(f"\n📚 Processing book: {self.file_path}")
        converter = self._build_converter()

        process_start = time.time()
        docling_doc = converter.convert(self.file_path).document
        process_time = time.time() - process_start
        print(f"✅ Book processed in {process_time:.2f}s")

        text = docling_doc.export_to_markdown()

        metadata = {
            "source": self.file_path,
            "format": "book",
            "process_time": process_time,
        }
        yield LCDocument(page_content=text, metadata=metadata)
