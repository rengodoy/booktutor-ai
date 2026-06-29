FROM ubuntu:noble

# --- System deps + Tesseract OCR (best-quality por/eng language packs) -------
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget gnupg2 lsb-release apt-transport-https curl ca-certificates \
        libtesseract-dev libleptonica-dev pkg-config \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN echo "deb https://notesalexp.org/tesseract-ocr5/noble/ noble main" \
        | tee /etc/apt/sources.list.d/notesalexp.list \
    && wget -O - https://notesalexp.org/debian/alexp_key.asc | apt-key add - \
    && apt-get update -oAcquire::AllowInsecureRepositories=true \
    && apt-get install -y --allow-unauthenticated notesalexp-keyring \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-por-best tesseract-ocr-eng-best \
    && rm -rf /var/lib/apt/lists/*

# --- uv ----------------------------------------------------------------------
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON=3.13 \
    HF_HOME=/hf-cache \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install dependencies first (better layer caching), then the project. docling is
# image-only now (not a default group), so install it explicitly.
# .python-version pins CPython 3.13 (faiss-cpu has no 3.14 wheel yet).
COPY pyproject.toml uv.lock README.md .python-version ./
RUN uv sync --frozen --no-install-project --no-dev --group docling

COPY . .
RUN uv sync --frozen --no-dev --group docling

# Default: run the docling OCR HTTP server (the easyocr/tesseract source tiers).
EXPOSE 8002
CMD ["glyph-docling-server"]
