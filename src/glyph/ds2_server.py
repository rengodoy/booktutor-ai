"""Standalone HTTP OCR server for DeepSeek-OCR-2.

The ``deepseek2`` engine needs ``transformers <4.48`` and can't share a venv
with docling (transformers 5). Exposing it as a tiny HTTP service lets the
``merge`` engine (which runs in the docling image) use DeepSeek-OCR-2 as a source
tier without the conflict. The heavy model loads once at startup.

Run it (in the deepseek2 extra / image):

    glyph-deepseek2-server          # uvicorn on DS2_SERVER_HOST:DS2_SERVER_PORT

Endpoints:
    GET  /health -> {"status": "ok", "model": "<id>"}
    POST /ocr    -> {"markdown": "..."}
        body: {"image_b64": "<base64 png/jpg>",
               "prompt"?, "base_size"?, "image_size"?, "crop_mode"?}
"""

from __future__ import annotations

import base64
import os
import tempfile

from pydantic import BaseModel

from glyph.config import Settings


class OcrRequest(BaseModel):
    image_b64: str
    prompt: str | None = None
    base_size: int | None = None
    image_size: int | None = None
    crop_mode: bool | None = None


class OcrResponse(BaseModel):
    markdown: str


def create_app():
    """Build the FastAPI app, loading the model once at import/startup."""
    from fastapi import FastAPI, HTTPException

    from glyph.loaders import deepseek2_ocr_image, load_deepseek2_model

    settings = Settings()

    print(
        f"⏳ Loading DeepSeek-OCR-2: {settings.ds2_model} (attn={settings.ds2_attn_impl})"
    )
    model, tokenizer = load_deepseek2_model(settings.ds2_model, settings.ds2_attn_impl)
    print("✅ Model loaded; server ready.")

    app = FastAPI(title="glyph DeepSeek-OCR-2", version="1.0")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "model": settings.ds2_model}

    @app.post("/ocr", response_model=OcrResponse)
    def ocr(req: OcrRequest) -> OcrResponse:
        try:
            image_bytes = base64.b64decode(req.image_b64)
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=400, detail=f"invalid image_b64: {exc}"
            ) from exc

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "page.png")
            with open(path, "wb") as fh:
                fh.write(image_bytes)
            markdown = deepseek2_ocr_image(
                model,
                tokenizer,
                path,
                prompt=req.prompt or settings.ds2_prompt,
                base_size=req.base_size or settings.ds2_base_size,
                image_size=req.image_size or settings.ds2_image_size,
                crop_mode=settings.ds2_crop_mode
                if req.crop_mode is None
                else req.crop_mode,
            )
        return OcrResponse(markdown=markdown)

    return app


def main() -> None:
    import uvicorn

    settings = Settings()
    uvicorn.run(
        create_app(),
        host=settings.ds2_server_host,
        port=settings.ds2_server_port,
    )


if __name__ == "__main__":
    main()
