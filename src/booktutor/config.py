"""Runtime configuration loaded from environment variables / a ``.env`` file.

Everything that tunes the OCR pipeline lives here. Point the ``VLM_OCR_*``
variables at any OpenAI-compatible vision endpoint when using the ``vlm`` engine.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from the environment or a ``.env`` file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- OCR ---------------------------------------------------------------
    # Engine (manual escalation when quality is poor):
    #   "easyocr"   -> docling + EasyOCR             (local-friendly, GPU)
    #   "tesseract" -> docling + Tesseract           (Docker: lang packs installed)
    #   "vlm"       -> DeepSeek-OCR via vLLM         (Docker: best on bad scans)
    #   "deepseek2" -> DeepSeek-OCR-2 in-process     (transformers, needs CUDA GPU)
    #   "none"      -> trust the PDF text layer      (no OCR)
    ocr_engine: str = Field(default="easyocr")
    # Comma-separated language codes (easyocr: "pt,en"; tesseract auto-mapped).
    ocr_languages: str = Field(default="en")
    # Re-OCR the whole page, ignoring a broken/garbled embedded text layer.
    ocr_force_full_page: bool = Field(default=False)
    ocr_num_threads: int = Field(default=8)

    # --- VLM-OCR (DeepSeek-OCR served by vLLM, OpenAI-compatible vision) ----
    vlm_ocr_api_base: str = Field(default="http://localhost:8000/v1")
    vlm_ocr_api_key: str = Field(default="not-needed")
    vlm_ocr_model: str = Field(default="unsloth/DeepSeek-OCR")
    vlm_ocr_prompt: str = Field(default="Free OCR.")
    # Output tokens per page. Must leave room for image+prompt input within the
    # vLLM --max-model-len (e.g. 4096 out + image tokens < 8192).
    vlm_ocr_max_tokens: int = Field(default=4096)
    vlm_ocr_dpi: int = Field(default=144)

    # --- DeepSeek-OCR-2 (in-process via transformers, trust_remote_code) ----
    # Unsloth alt: DS2_MODEL=unsloth/DeepSeek-OCR-2 (use DS2_IMAGE_SIZE=640).
    ds2_model: str = Field(default="deepseek-ai/DeepSeek-OCR-2")
    ds2_prompt: str = Field(
        default="<image>\n<|grounding|>Convert the document to markdown."
    )
    ds2_base_size: int = Field(default=1024)
    ds2_image_size: int = Field(default=768)
    ds2_crop_mode: bool = Field(default=True)
    # "eager" runs anywhere; "flash_attention_2" is faster but needs flash-attn.
    ds2_attn_impl: str = Field(default="eager")
    ds2_dpi: int = Field(default=144)

    @property
    def ocr_language_list(self) -> list[str]:
        return [lang.strip() for lang in self.ocr_languages.split(",") if lang.strip()]
