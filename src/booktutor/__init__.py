"""BookTutor — OCR any PDF into high-quality Markdown.

Runs docling (EasyOCR / Tesseract) or a vision model (DeepSeek-OCR via vLLM)
to turn scanned or text-layer PDFs into Markdown. Configure it through
environment variables / a ``.env`` file — see :class:`booktutor.config.Settings`.
"""

from booktutor.config import Settings

__all__ = ["Settings"]
__version__ = "0.4.0"
