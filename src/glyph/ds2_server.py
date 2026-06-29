"""Standalone HTTP OCR server for DeepSeek-OCR-2.

The ``deepseek2`` engine needs ``transformers <4.48`` and can't share a venv
with docling (transformers 5). Exposing it as a tiny HTTP service lets the thin
local orchestrator use DeepSeek-OCR-2 as a source tier without the conflict. The
heavy model loads once in a background thread so the server binds immediately and
``/status`` can report the (minutes-long) cold start while ``/health`` stays 503.

Run it (in the deepseek2 group / image):

    glyph-deepseek2-server          # uvicorn on DS2_SERVER_HOST:DS2_SERVER_PORT

Endpoints:
    GET  /health -> 200 {"status":"ok","model":"<id>"} once loaded, else 503
    GET  /status -> {"ready": bool, "stage": "loading|ready", "progress": float|null}
    POST /ocr    -> {"markdown": "..."}
        body: {"image_b64": "<base64 png/jpg>",
               "prompt"?, "base_size"?, "image_size"?, "crop_mode"?}
"""

from __future__ import annotations

import base64
import contextlib
import io
import os
import tempfile
import threading

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


def load_deepseek2_model(model_id: str, attn_impl: str = "eager"):
    """Load DeepSeek-OCR-2 (model, tokenizer) onto CUDA via transformers."""
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


def create_app():
    """Build the FastAPI app, loading the model once in a background thread."""
    from fastapi import FastAPI, HTTPException, Response

    settings = Settings()
    state: dict[str, object] = {"ready": False, "stage": "loading", "progress": None}
    holder: dict[str, object] = {}

    def _load() -> None:
        print(
            f"⏳ Loading DeepSeek-OCR-2: {settings.ds2_model} "
            f"(attn={settings.ds2_attn_impl})"
        )
        holder["model"], holder["tokenizer"] = load_deepseek2_model(
            settings.ds2_model, settings.ds2_attn_impl
        )
        state["ready"] = True
        state["stage"] = "ready"
        print("✅ Model loaded; server ready.")

    app = FastAPI(title="glyph DeepSeek-OCR-2", version="1.0")

    @app.on_event("startup")
    def _startup() -> None:
        threading.Thread(target=_load, daemon=True).start()

    @app.get("/health")
    def health():
        if not state["ready"]:
            return Response(status_code=503)
        return {"status": "ok", "model": settings.ds2_model}

    @app.get("/status")
    def status() -> dict:
        return dict(state)

    @app.post("/ocr", response_model=OcrResponse)
    def ocr(req: OcrRequest) -> OcrResponse:
        if not state["ready"]:
            raise HTTPException(status_code=503, detail="model still loading")
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
                holder["model"],
                holder["tokenizer"],
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
