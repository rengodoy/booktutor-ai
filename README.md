# Glyph — PDF → Markdown OCR

OCR any PDF (scanned or text-layer) into clean **Markdown** with **one adaptive
command**. Glyph starts on the simplest OCR engine and a **Vision-LLM judges
every page**, escalating to stronger engines only when confidence is low — and
it tells you each time it does. One `.md` file per PDF.

> This tool does **one thing**: high-quality OCR → Markdown. No chat, no RAG.

## The command

```bash
glyph extract books/livro.pdf      # writes books/livro.md
```

`glyph` runs **locally** as a thin orchestrator (no torch/docling/transformers
installed). Each page runs the cheapest engine first; the Vision-LLM reconciler
reads the page image plus the candidate text, returns the best Markdown and a
confidence. If confidence is below `MERGE_MIN_CONFIDENCE`, Glyph escalates to the
next tier and prints it — with a live page progress bar:

```
page 1/12: easyocr → confidence 0.94 ✓
page 2/12: easyocr → confidence 0.61 — escalating to tesseract
page 2/12: tesseract → confidence 0.71 — escalating to easyocr+tesseract
page 2/12: easyocr+tesseract → confidence 0.89 ✓
```

## Architecture — thin local orchestrator + on-demand engine services

`glyph` holds no ML deps. The OCR engines are HTTP services in containers that it
**spins up on demand** and **stops at the end** (only the ones it started):

```
  glyph (LOCAL host process — pydantic-settings + openai + pypdfium2 + rich)
    │  rasterize each page (pypdfium2)
    │  per page, walk the tier ladder:
    │   ├─ easyocr / tesseract ─HTTP─► docling service  :8002  (docker compose up -d, on demand)
    │   ├─ deepseek2           ─HTTP─► deepseek2 service :8001  (on demand, GPU1)
    │   └─ none                ─ local pypdfium2 text layer (no service)
    │  judge / reconcile each page ─HTTP─► Vision-LLM (HOST, GPU0, already running :8080)
    └─ at the end: docker compose stop <the services it started>   (frees VRAM)
```

* **`glyph` (local)** — the orchestrator + the `merge` adaptive pipeline. The only
  thing you install on the host. Talks to everything over HTTP.
* **`docling` service** — easyocr/tesseract OCR over HTTP (Tesseract lang packs
  baked in). CPU by default — it's the cheap early tier.
* **`deepseek2` service** — DeepSeek-OCR-2 over HTTP, pinned to GPU1. Its remote
  code needs `transformers <4.48` (conflicts with docling's transformers 5), so it
  lives in a separate image. The strongest tier of the ladder.
* **Vision-LLM reconciler** — an OpenAI-compatible vision endpoint you run on the
  host (e.g. llama.cpp serving `gemma-qat`) on GPU0. Not in compose.

The orchestrator brings a service up the first time the ladder needs it, polls its
`/health` (showing a **model-load spinner / bar** from `/status` during the cold
start), keeps it up for the rest of the PDF, and stops it on exit — including on
Ctrl-C. A service you started yourself is reused and **left running**.

## Setup

```bash
uv sync                    # thin local install (orchestrator only — no torch)
cp .env.example .env       # defaults target the published service ports on 127.0.0.1
docker compose build       # builds the docling + deepseek2 images (one-time)
```

Start your **Vision-LLM** on the host at `:8080` (serving `MERGE_MODEL`, e.g.
`gemma-qat`, on GPU0). Then extract — engine services start on demand:

```bash
glyph extract books/livro.pdf
```

> If the host Vision-LLM is down, the default `merge` engine fails fast with a
> clear message (`MERGE_API_BASE` is required). If a single engine service won't
> start, that tier is skipped and the run continues with the other engines.

Useful flags: `--keep-up` (leave the services running for the next run),
`--no-autostart` (assume the services are already up; don't spin them).

## Tuning the ladder

All config is environment variables / `.env` (see [`.env.example`](.env.example)):

| Variable | What it does |
|---|---|
| `MERGE_TIERS` | escalation ladder, simplest→strongest. `;`-separated tiers, each a `,`-list of engines. Default: `easyocr;tesseract;easyocr,tesseract;easyocr,tesseract,deepseek2` |
| `MERGE_MIN_CONFIDENCE` | escalate while the reconciler's confidence is below this (default `0.85`) |
| `MERGE_PROSE` | `true` (default) reflows body text into continuous prose — strips page numbers / running headers-footers, joins words split across lines, and stitches a sentence/word split across a page break; `false` keeps the page's literal line breaks |
| `MERGE_IMAGES` | `true` (default) extracts figures embedded in the PDF as PNGs into a sibling `<name>.assets/` dir and points the markdown image links at them so they render; `false` leaves figures out |
| `MERGE_MIN_FIGURE_PT` | minimum displayed size (PDF points) for an embedded image to count as a figure — filters icons / bullets / header strips (default `72`, i.e. 1 inch) |
| `MERGE_MODEL` | the Vision-LLM reconciler/judge (default `gemma-qat`) |
| `MERGE_API_BASE` | the reconciler endpoint (default the host: `http://127.0.0.1:8080/v1`) |
| `MERGE_DOCLING_URL` / `MERGE_DEEPSEEK2_URL` | the on-demand engine services (default `127.0.0.1:8002` / `:8001`) |
| `SERVICE_AUTOSTART` / `SERVICE_STOP_ON_EXIT` | spin services up on demand / stop the ones we started (default both `true`) |
| `OCR_LANGUAGES` | OCR languages, e.g. `pt,en` |
| `OCR_FORCE_FULL_PAGE` | `true` re-OCRs from the page image, ignoring a garbled embedded text layer — the single biggest fix for mojibake like `CONTEœDO`/`sªo` |

### Pin a single engine (skip escalation)

For debugging or a known-good scan, force one engine — it becomes a one-tier
ladder through the same orchestrator (the Vision-LLM still reconciles the single
candidate):

```bash
# in .env: OCR_ENGINE=tesseract   (or easyocr | none | deepseek2)
glyph extract books/livro.pdf
```

`OCR_ENGINE=none` uses the PDF's own embedded text layer (no OCR service, no GPU).

## Development — edit code, no rebuild

`./src` is bind-mounted into both service images over the editable install, so
server code changes take effect on the next `docker compose up` — only
`pyproject.toml`/lockfile changes need a rebuild. Orchestrator changes are live
(it runs from your local `uv` env).

Run the tests (lazy imports, so no heavy deps needed):

```bash
uv run pytest
uv run ruff check
```

### Running the engine services standalone

```bash
docker compose up -d docling      # easyocr/tesseract OCR HTTP server :8002
docker compose up -d deepseek2    # DeepSeek-OCR-2 HTTP server :8001 (GPU1)
```

## GPU / VRAM

DeepSeek-OCR-2 inference takes ≈14.5 GB — about a full 16 GB GPU. On a 2×16 GB
box: the Vision-LLM reconciler runs on **GPU0**, `deepseek2` is pinned to **GPU1**
(`device_ids: ['1']` in `docker-compose.yaml`), and `docling` runs on **CPU**
(it's the cheap early tier; Tesseract is CPU anyway). A small reconciler
(`MERGE_MODEL=gemma-qat`) reconciles as well as a 27B here and leaves room. To put
docling on GPU0 if there's headroom, uncomment its `deploy` block.

> ⚠️ vLLM doesn't yet serve DeepSeek-OCR-2 on CUDA (`DeepseekOCR2ForCausalLM`
> unsupported; vLLM issue #41468) — that's why this tier is a transformers
> in-process server. `flash-attn` is optional; the default `eager` works everywhere.

## Project layout

```
src/glyph/
├── config.py          # Settings from env / .env (pydantic-settings)
├── progress.py        # ProgressReporter event contract + ConsoleReporter (rich)
├── services.py        # ServiceManager: on-demand `docker compose up/stop`
├── loaders.py         # MergeOcrLoader — the thin adaptive orchestrator
├── docling_server.py  # docling OCR HTTP server (easyocr/tesseract tiers)
├── ds2_server.py      # DeepSeek-OCR-2 HTTP server (the deepseek2 tier)
└── cli.py             # extract
tests/                 # config / loaders / services / progress / servers
Dockerfile             # docling image (easyocr/tesseract) — glyph-docling-server
Dockerfile.deepseek2   # DeepSeek-OCR-2 image — glyph-deepseek2-server
```

## Requirements

- Python 3.13+ with [`uv`](https://docs.astral.sh/uv/) on the host (thin install)
- Docker — for the OCR engine services
- A CUDA GPU (~16 GB) for the `deepseek2` tier; weights cached in the `hf-cache` volume
- An OpenAI-compatible **Vision-LLM** on the host for the `merge` reconciler
```
