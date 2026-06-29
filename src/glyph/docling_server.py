"""Standalone HTTP OCR server for the docling engines (easyocr / tesseract).

docling pulls in heavy ML deps (torch) that conflict with DeepSeek-OCR-2's
``transformers <4.48``, so it ships in its own image (Dockerfile) and the thin
local orchestrator talks to it over HTTP. The orchestrator rasterizes each PDF
page and POSTs the PNG to ``/ocr``; this server runs docling on the single image.

Run it (in the docling group / image):

    glyph-docling-server            # uvicorn on DOCLING_SERVER_HOST:DOCLING_SERVER_PORT

Endpoints:
    GET  /health -> 200 {"status":"ok","engine":"docling"} once warm, else 503
    GET  /status -> {"ready": bool, "stage": "loading|ready", "progress": float|null}
    POST /ocr    -> {"markdown": "..."}
        body: {"image_b64": "<base64 png>", "engine"?, "languages"?, "force_full_page"?}

Module-top imports stay light (pydantic only) so tests import the request/response
models and the language map without docling installed.
"""

from __future__ import annotations

import base64
import os
import tempfile
import threading

from pydantic import BaseModel

from glyph.config import Settings

# easyocr code -> tesseract code
_TESSERACT_LANG = {
    "pt": "por",
    "en": "eng",
    "es": "spa",
    "fr": "fra",
    "de": "deu",
    "it": "ita",
}


class DoclingOcrRequest(BaseModel):
    image_b64: str
    engine: str = "easyocr"  # easyocr | tesseract | none
    languages: list[str] = ["en"]
    force_full_page: bool = False


class DoclingOcrResponse(BaseModel):
    markdown: str


def make_docling_converter(
    ocr_engine: str,
    *,
    ocr_languages: list[str] | None = None,
    force_full_page_ocr: bool = False,
    num_threads: int = 8,
):
    """Build a docling ``DocumentConverter`` that OCRs a PDF **or a single image**.

    ``ocr_engine`` is ``easyocr`` | ``tesseract`` | ``none``. Both the PDF and
    IMAGE input formats are registered with the same pipeline so a rasterized page
    PNG runs through the identical OCR/layout/table options.
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
    from docling.document_converter import (
        DocumentConverter,
        ImageFormatOption,
        PdfFormatOption,
    )

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
            InputFormat.IMAGE: ImageFormatOption(pipeline_options=pipeline_options),
        }
    )


def _ocr_image_bytes(converter, image_bytes: bytes) -> str:
    """OCR one image (PNG bytes) with a docling converter -> markdown."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "page.png")
        with open(path, "wb") as fh:
            fh.write(image_bytes)
        return converter.convert(path).document.export_to_markdown()


def create_app():
    """Build the FastAPI app; warm the default easyocr converter in the background.

    ``/health`` stays 503 until the warm-up finishes so the orchestrator's startup
    spinner reflects the (one-time) easyocr model download; ``/status`` reports the
    stage meanwhile.
    """
    from fastapi import FastAPI, HTTPException, Response

    settings = Settings()

    # Cache one converter per (engine, langs, force_full_page) — EasyOCR/Tesseract
    # load once and are reused across the hundreds of per-page /ocr calls.
    converters: dict[tuple, object] = {}
    state: dict[str, object] = {"ready": False, "stage": "loading", "progress": None}

    def _converter(engine: str, languages: list[str], force_full_page: bool):
        key = (engine, tuple(languages), force_full_page)
        if key not in converters:
            converters[key] = make_docling_converter(
                engine,
                ocr_languages=languages,
                force_full_page_ocr=force_full_page,
                num_threads=settings.ocr_num_threads,
            )
        return converters[key]

    def _warm() -> None:
        # Build + exercise the default easyocr converter so the model download
        # happens now (visible as the startup spinner), not on the first page.
        try:
            from PIL import Image

            conv = _converter("easyocr", settings.ocr_language_list, False)
            buf = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            try:
                Image.new("RGB", (64, 64), "white").save(buf.name)
                conv.convert(buf.name)
            finally:
                os.unlink(buf.name)
        except Exception:  # noqa: BLE001 — warm is best-effort; serve anyway
            pass
        finally:
            state["ready"] = True
            state["stage"] = "ready"

    app = FastAPI(title="glyph docling OCR", version="1.0")

    @app.on_event("startup")
    def _startup() -> None:
        threading.Thread(target=_warm, daemon=True).start()

    @app.get("/health")
    def health():
        if not state["ready"]:
            return Response(status_code=503)
        return {"status": "ok", "engine": "docling"}

    @app.get("/status")
    def status() -> dict:
        return dict(state)

    @app.post("/ocr", response_model=DoclingOcrResponse)
    def ocr(req: DoclingOcrRequest) -> DoclingOcrResponse:
        try:
            image_bytes = base64.b64decode(req.image_b64)
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=400, detail=f"invalid image_b64: {exc}"
            ) from exc
        conv = _converter(req.engine, req.languages, req.force_full_page)
        return DoclingOcrResponse(markdown=_ocr_image_bytes(conv, image_bytes))

    return app


def main() -> None:
    import uvicorn

    settings = Settings()
    uvicorn.run(
        create_app(),
        host=settings.docling_server_host,
        port=settings.docling_server_port,
    )


if __name__ == "__main__":
    main()
