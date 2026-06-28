# BookTutor — PDF → Markdown OCR

OCR any PDF (scanned or text-layer) into clean **Markdown**. It runs `docling`
with a choice of OCR engines — **EasyOCR**, **Tesseract**, or a vision model
(**DeepSeek-OCR** served by vLLM) — and writes one `.md` file per PDF.

> This tool does **one thing**: high-quality OCR → Markdown. No chat, no RAG.

## How it works

`extract` converts a PDF to Markdown using the engine selected by `OCR_ENGINE`:

```bash
booktutor extract livro.pdf            # writes livro.md
booktutor extract livro.pdf -o out.md  # custom output path
```

## OCR engines (`OCR_ENGINE`)

Pick the engine and **escalate manually** if the text comes out poor
(worst → best on bad scans):

| `OCR_ENGINE` | Quality on bad scans | Where to run |
|---|---|---|
| `none`      | — (uses the PDF's own text layer) | local |
| `easyocr`   | good (GPU) | **local (uv)** |
| `tesseract` | good, classic | **Docker** (lang packs installed) |
| `vlm`       | best — DeepSeek-OCR reads the page image | **Docker** (vLLM service) |
| `deepseek2` | best — DeepSeek-OCR-2 (DeepEncoder V2), in-process | local/Docker, **CUDA GPU** |

Set `OCR_FORCE_FULL_PAGE=true` to **ignore a garbled embedded text layer** and
re-OCR from the page images — the single biggest fix for mojibake like
`CONTEœDO`/`sªo`. Pick languages with `OCR_LANGUAGES` (e.g. `pt,en`).

All settings come from environment variables / a `.env` file — see
[`.env.example`](.env.example).

---

## Option A — Docker (recommended)

Docker is the primary way to run this: Tesseract lang packs are baked into the
image and the VLM engine (DeepSeek-OCR via vLLM) is wired up in compose. Put
PDFs in `./books`; extracted Markdown is written next to each PDF. Config comes
from `.env`.

```bash
cp .env.example .env   # then edit OCR_ENGINE / OCR_LANGUAGES
docker compose build   # builds the docling image (easyocr/tesseract/vlm)
```

> The `deepseek2` engine has its own image — build it with
> `docker compose --profile deepseek2 build deepseek2` (see below).

### Tesseract OCR

Set `OCR_ENGINE=tesseract` and `OCR_LANGUAGES=pt,en` in `.env`, then:

```bash
docker compose run --rm booktutor extract books/livro.pdf
```

### VLM OCR (DeepSeek-OCR via vLLM)

Best quality on degraded scans. Start the vLLM service (the `vlm` profile),
point the app at it, and extract. In `.env`:

```dotenv
OCR_ENGINE=vlm
VLM_OCR_API_BASE=http://deepseek-ocr:8000/v1   # the compose service name
VLM_OCR_MODEL=unsloth/DeepSeek-OCR
```

```bash
# 1. bring up the OCR model server (first run downloads the weights — large)
docker compose --profile vlm up -d deepseek-ocr

# 2. extract through it
docker compose run --rm booktutor extract books/livro.pdf
```

> ⚠️ DeepSeek-OCR needs a recent/nightly vLLM. If the model fails to load,
> adjust the image tag or flags on the `deepseek-ocr` service in
> `docker-compose.yaml` (see the
> [Unsloth guide](https://unsloth.ai/docs/models/tutorials/deepseek-ocr-how-to-run-and-fine-tune)).

### DeepSeek-OCR-2 (in-process, its own image)

`OCR_ENGINE=deepseek2` runs **DeepSeek-OCR-2** (DeepEncoder V2) directly in the
process via transformers (`trust_remote_code`) — no inference server. Needs a
**CUDA GPU**; the weights download once and are cached by Hugging Face.

It ships as a **separate image** (`Dockerfile.deepseek2`, compose service
`deepseek2`, profile `deepseek2`) because its remote code needs
`transformers <4.48` (`LlamaFlashAttention2`), which conflicts with docling 2.10x
(needs transformers 5, `rt_detr_v2`). The two can't share a venv, so each lives
in its own uv extra (`booktutor[docling]` vs `booktutor[deepseek2]`).

In `.env`:

```dotenv
OCR_ENGINE=deepseek2
DS2_MODEL=deepseek-ai/DeepSeek-OCR-2   # or unsloth/DeepSeek-OCR-2 (set DS2_IMAGE_SIZE=640)
DS2_ATTN_IMPL=eager                    # "flash_attention_2" is faster but needs flash-attn
```

```bash
docker compose --profile deepseek2 build deepseek2
docker compose --profile deepseek2 run --rm deepseek2 extract books/livro.pdf
```

Locally (its own extra; do **not** mix with the docling extra):

```bash
uv sync --extra deepseek2
uv run --extra deepseek2 booktutor extract livro.pdf
```

> ⚠️ vLLM doesn't yet serve DeepSeek-OCR-2 on CUDA (`DeepseekOCR2ForCausalLM`
> not supported; vLLM issue #41468), which is why this path is in-process.
> `flash-attn` is optional: the default `eager` works everywhere.

**GPU sizing.** DeepSeek-OCR is ~3B params — it fits comfortably in **16 GB**
(e.g. an RTX 5080 or RTX 2000 Ada), single GPU, no tensor-parallel. With two
GPUs, pin the OCR server to one and leave the other for the app (docling) to
avoid contention, e.g. set `device_ids: ['0']` on `deepseek-ocr` and `['1']` on
`booktutor` in `docker-compose.yaml` (replacing `count: all`). Drop the
`deploy.resources` block entirely to run CPU-only (much slower).

---

## Option B — Local with uv + venv

The OCR engines live in **mutually-exclusive extras** — install one:

- `--extra docling` → `easyocr` / `tesseract` / `none` / `vlm` engines
- `--extra deepseek2` → the `deepseek2` engine (separate transformers)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # install uv (once)
uv sync --extra docling                            # build .venv (docling engines)
cp .env.example .env                               # set OCR_ENGINE / OCR_LANGUAGES

uv run --extra docling booktutor extract livro.pdf # writes livro.md
```

For DeepSeek-OCR-2, swap the extra (don't mix the two in one venv):

```bash
uv sync --extra deepseek2
uv run --extra deepseek2 booktutor extract livro.pdf
```

Prefer an activated shell? That works too:

```bash
source .venv/bin/activate
booktutor extract livro.pdf
python -m booktutor extract livro.pdf   # equivalent module form
deactivate
```

### Development

```bash
uv run pytest        # run the test suite (no extra needed — imports are lazy)
uv run ruff check    # lint
```

---

## Project layout

```
src/booktutor/
├── config.py        # Settings from env / .env (pydantic-settings)
├── loaders.py       # make_loader(): docling / VLM / DeepSeek-OCR-2
└── cli.py           # extract
tests/               # config + loader selection
Dockerfile           # docling image (easyocr/tesseract/vlm)
Dockerfile.deepseek2 # DeepSeek-OCR-2 image (separate transformers)
```

The OCR engines live in two **mutually-exclusive** uv extras — `docling`
(transformers 5) and `deepseek2` (transformers <4.48) — declared as conflicting
in `pyproject.toml`, so they never share a venv.

## Requirements

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/) (recommended) — or Docker
- For `vlm`: an OpenAI-compatible vision endpoint serving DeepSeek-OCR
  (the bundled `deepseek-ocr` compose service)
- For `deepseek2`: a CUDA GPU (~16 GB); weights download once and are cached
