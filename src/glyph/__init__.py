"""Glyph — OCR any PDF into high-quality Markdown.

One adaptive command (``merge``): start on the simplest engine — docling
(EasyOCR / Tesseract) — and let a Vision-LLM judge each page and escalate to
DeepSeek-OCR-2 when confidence is low. Configure it through environment
variables / a ``.env`` file — see :class:`glyph.config.Settings`.
"""

from glyph.config import Settings

__all__ = ["Settings"]
__version__ = "0.4.0"
