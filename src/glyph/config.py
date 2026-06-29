"""Runtime configuration loaded from environment variables / a ``.env`` file.

Everything that tunes the OCR pipeline lives here. Point the ``MERGE_API_BASE``
variable at any OpenAI-compatible vision endpoint for the ``merge`` reconciler.

``glyph`` runs locally as a thin orchestrator; the OCR engines are on-demand
HTTP services (docling :8002, deepseek2 :8001) it spins up via docker compose.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from the environment or a ``.env`` file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- OCR ---------------------------------------------------------------
    # Engine. Default "merge" is the one adaptive command: start on the simplest
    # engine, let a Vision-LLM judge each page and escalate the ladder only when
    # confidence is low (it prints when it does). Pin a single engine to disable
    # escalation / for debugging:
    #   "merge"     -> adaptive ladder + Vision-LLM reconciler  (DEFAULT)
    #   "easyocr"   -> docling + EasyOCR             (local-friendly, GPU)
    #   "tesseract" -> docling + Tesseract           (Docker: lang packs installed)
    #   "deepseek2" -> DeepSeek-OCR-2 in-process     (transformers, needs CUDA GPU)
    #   "none"      -> trust the PDF text layer      (no OCR)
    ocr_engine: str = Field(default="merge")
    # Comma-separated language codes (easyocr: "pt,en"; tesseract auto-mapped).
    ocr_languages: str = Field(default="en")
    # Re-OCR the whole page, ignoring a broken/garbled embedded text layer.
    ocr_force_full_page: bool = Field(default=False)
    ocr_num_threads: int = Field(default=8)

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
    # Standalone DeepSeek-OCR-2 HTTP server (glyph-deepseek2-server). Lets
    # the merge engine use deepseek2 as a source without the venv conflict.
    ds2_server_host: str = Field(default="0.0.0.0")
    ds2_server_port: int = Field(default=8001)

    # --- docling HTTP service (glyph-docling-server) ------------------------
    # The easyocr/tesseract engines run as an on-demand HTTP service (CPU by
    # default). The orchestrator POSTs a rasterized page image to /ocr.
    docling_server_host: str = Field(default="0.0.0.0")
    docling_server_port: int = Field(default=8002)
    merge_docling_url: str = Field(default="http://127.0.0.1:8002")

    # --- on-demand service lifecycle (docker compose, from the host) --------
    # The orchestrator spins each engine service up the first time the ladder
    # needs it, polls /health, and stops the ones it started at the end.
    compose_file: str = Field(default="docker-compose.yaml")
    compose_project_name: str = Field(default="")  # optional `docker compose -p`
    service_autostart: bool = Field(default=True)  # spin services on demand
    service_stop_on_exit: bool = Field(default=True)  # stop the ones we started
    docling_health_timeout: float = Field(default=180.0)  # easyocr 1st-run download
    deepseek2_health_timeout: float = Field(default=600.0)  # ds2 model load (minutes)
    health_poll_interval: float = Field(default=2.0)

    # --- Merge (adaptive multi-engine OCR reconciled by a Vision-LLM) -------
    # Escalation ladder: ';'-separated tiers, each a ','-list of source engines
    # (docling engines: easyocr, tesseract). Each page escalates to the next tier
    # until the reconciler's confidence reaches merge_min_confidence (or the
    # tiers run out). The reconciler always also reads the page image.
    merge_tiers: str = Field(
        default="easyocr;tesseract;easyocr,tesseract;easyocr,tesseract,deepseek2"
    )
    merge_api_base: str = Field(default="http://127.0.0.1:8080/v1")
    merge_api_key: str = Field(default="not-needed")
    # A small vision model leaves GPU room for the deepseek2 tier; gemma-qat
    # reconciles as well as the 27B here. Swap to a bigger one if you have VRAM.
    merge_model: str = Field(default="gemma-qat")
    merge_max_tokens: int = Field(default=8192)
    merge_dpi: int = Field(default=144)
    merge_min_confidence: float = Field(default=0.85)
    # The "deepseek2" source tier calls the standalone DeepSeek-OCR-2 HTTP server
    # (glyph-deepseek2-server / compose service `deepseek2`). Empty/down ->
    # that candidate is skipped (the run continues with the other engines).
    merge_deepseek2_url: str = Field(default="http://127.0.0.1:8001")

    @field_validator("compose_project_name", mode="after")
    @classmethod
    def _clean_project_name(cls, v: str) -> str:
        # python-dotenv keeps an inline comment as the value when the value is
        # empty (``COMPOSE_PROJECT_NAME=   # note`` -> ``# note``); strip it so a
        # commented-out / blank setting really means "no -p flag".
        return v.split("#", 1)[0].strip()

    @property
    def compose_file_path(self) -> str:
        """Absolute path to the compose file, resolved in this order.

        ``$GLYPH_COMPOSE_FILE`` env > ``compose_file`` (if it exists relative to
        cwd) > the repo root sitting next to the installed ``glyph`` package. So
        ``glyph extract`` works from any working directory.
        """
        env = os.environ.get("GLYPH_COMPOSE_FILE")
        if env:
            return str(Path(env).expanduser().resolve())
        cwd_candidate = Path(self.compose_file)
        if cwd_candidate.exists():
            return str(cwd_candidate.resolve())
        # src/glyph/config.py -> repo root is three parents up.
        repo_root = Path(__file__).resolve().parents[2]
        return str(repo_root / self.compose_file)

    @property
    def ocr_language_list(self) -> list[str]:
        return [lang.strip() for lang in self.ocr_languages.split(",") if lang.strip()]

    @property
    def merge_tier_list(self) -> list[list[str]]:
        tiers: list[list[str]] = []
        for tier in self.merge_tiers.split(";"):
            engines = [e.strip() for e in tier.split(",") if e.strip()]
            if engines:
                tiers.append(engines)
        return tiers
