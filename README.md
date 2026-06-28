# BookTutor AI — Convert Any Book into an AI Tutor

Transform any PDF book into an interactive AI tutor that answers questions and
explains concepts using **RAG** (Retrieval-Augmented Generation).

> Originally an explainer project — see https://youtu.be/GTidrAiojbg for the
> video that started it. This version is provider-agnostic and rebuilt around
> the OpenAI API standard.

## How it works

1. **Ingest** — `docling` converts the PDF (OCR included for scanned books) to
   markdown.
2. **Index** — the text is chunked, embedded, and stored in a local **FAISS**
   vector store, organised as named *collections*.
3. **Chat** — your questions retrieve the most relevant chunks (MMR search) and
   an LLM answers from that context, keeping the conversation history.

Both the LLM **and** the embeddings speak the **OpenAI API standard**, so you can
point them at any compatible endpoint — OpenAI, Azure OpenAI, vLLM, LM Studio,
Ollama, llama.cpp / llama-swap, etc. Nothing is hardcoded to a single provider.

## Configuration

All settings come from environment variables / a `.env` file (see
[`.env.example`](.env.example) for the full list). The important part is the two
endpoints — **chat** and **embeddings** — which can be the same server or two
different ones:

```dotenv
# Chat LLM
LLM_API_BASE=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini

# Embeddings backend: "openai" (an endpoint) or "local" (in-process, no server)
EMBEDDING_BACKEND=openai
EMBEDDING_API_BASE=          # for openai backend; empty = reuse the chat ones
EMBEDDING_API_KEY=
EMBEDDING_MODEL=text-embedding-3-small
LOCAL_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2  # for local backend
```

> 💡 **Embeddings need a source too, not just chat.** If your chat server
> doesn't serve embeddings (e.g. llama.cpp / llama-swap without `--embeddings`),
> set `EMBEDDING_BACKEND=local` to run a `sentence-transformers` model
> **in-process** — no extra server, port, or endpoint. See
> [Local embeddings](#local-embeddings).

---

## Running

There are two supported ways to run BookTutor: directly with **uv / venv**
(below) or inside a **Docker container** (further down).

## Option A — Local with uv + venv

### 1. Install uv (once)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Create the virtualenv and install everything

`uv sync` reads `pyproject.toml` + `uv.lock` and builds `.venv/` with the exact
pinned dependencies (PyTorch, docling, LangChain, FAISS, …):

```bash
uv sync
```

### 3. Configure your endpoints

```bash
cp .env.example .env
# then edit .env with your LLM/embeddings base URL, key and model
```

### 4. Run it

Use `uv run` to execute inside the venv without activating it:

```bash
# Ingest one or more PDFs into a named collection
uv run booktutor ingest livro.pdf -c livro

# Chat with it
uv run booktutor chat -c livro

# List collections you've already built
uv run booktutor list

# Show the retrieved source chunks alongside each answer
uv run booktutor chat -c livro --show-sources
```

#### Extract → review → ingest (optional)

OCR is never perfect. To **fix the text by hand before it reaches the LLM**,
extract to markdown, edit it, then ingest the reviewed file:

```bash
# 1. Extract the PDF to markdown (uses the configured OCR_ENGINE)
uv run booktutor extract livro.pdf            # writes livro.md

# 2. Open livro.md, fix any OCR mistakes, save

# 3. Ingest the reviewed text (no OCR — read as-is)
uv run booktutor ingest livro.md -c livro
```

`ingest` accepts `.md`/`.txt` directly, so the corrected text is what gets
chunked and embedded.

Prefer an activated shell? That works too:

```bash
source .venv/bin/activate
booktutor chat -c livro        # the `booktutor` command is on PATH now
python -m booktutor list       # equivalent module form
deactivate
```

Indexes are cached under `INDEX_DIR` (default `indexes/`), so each book is only
processed once; later runs load the FAISS store from disk.

### Local embeddings

If your LLM server does chat but **not** embeddings, set
`EMBEDDING_BACKEND=local`. A `sentence-transformers` model then runs
**in-process** — no separate server, port, or endpoint to manage:

```dotenv
LLM_API_BASE=http://127.0.0.1:8080/v1      # your chat server (e.g. llama-swap)
LLM_API_KEY=not-needed
LLM_MODEL=your-chat-model

EMBEDDING_BACKEND=local
LOCAL_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

The model is downloaded once (cached by Hugging Face) and reused. The required
deps (`langchain-huggingface`, `sentence-transformers`) ship with the project,
so `uv run booktutor ...` works as-is — nothing extra to install.

> 🌍 For non-English books, use a **multilingual** model, e.g.
> `LOCAL_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.

### OCR engines (`OCR_ENGINE`)

Bad scans / garbled PDF text layers? Pick the engine via `OCR_ENGINE` and
**escalate manually** if the text comes out poor (worst → best):

| `OCR_ENGINE` | Quality on bad scans | Where to run |
|---|---|---|
| `none`      | — (uses the PDF's own text layer) | local |
| `easyocr`   | good (GPU) | **local (uv)** |
| `tesseract` | good, classic | **Docker** (lang packs installed) |
| `vlm`       | best — DeepSeek-OCR reads the page image | **Docker** (vLLM service) |

Set `OCR_FORCE_FULL_PAGE=true` to **ignore a garbled embedded text layer** and
re-OCR from the page images — the single biggest fix for mojibake like
`CONTEœDO`/`sªo`. Pick languages with `OCR_LANGUAGES` (e.g. `pt,en`).

`easyocr` is the local default. `tesseract` and `vlm` are meant to run in
Docker (next section).

### Development

```bash
uv run pytest        # run the test suite
uv run ruff check    # lint
```

---

## Option B — Docker

Use Docker for the heavier OCR engines: **Tesseract** (lang packs baked into the
image) and **VLM** (DeepSeek-OCR served by vLLM). Put PDFs in `./books`;
collections persist in `./indexes`. Config comes from `.env`.

```bash
docker compose build
```

### Tesseract OCR

Set `OCR_ENGINE=tesseract` and `OCR_LANGUAGES=pt,en` in `.env`, then:

```bash
docker compose run --rm booktutor ingest books/livro.pdf -c livro
docker compose run --rm booktutor chat -c livro
docker compose run --rm booktutor list
```

### VLM OCR (DeepSeek-OCR via vLLM)

Best quality on degraded scans. Start the vLLM service (the `vlm` profile),
point the app at it, and ingest. In `.env`:

```dotenv
OCR_ENGINE=vlm
VLM_OCR_API_BASE=http://deepseek-ocr:8000/v1   # the compose service name
VLM_OCR_MODEL=unsloth/DeepSeek-OCR
```

```bash
# 1. bring up the OCR model server (first run downloads the weights — large)
docker compose --profile vlm up -d deepseek-ocr

# 2. ingest through it, then chat
docker compose run --rm booktutor ingest books/livro.pdf -c livro
docker compose run --rm booktutor chat -c livro
```

> ⚠️ DeepSeek-OCR needs a recent/nightly vLLM. If the model fails to load,
> adjust the image tag or flags on the `deepseek-ocr` service in
> `docker-compose.yaml` (see the
> [Unsloth guide](https://unsloth.ai/docs/models/tutorials/deepseek-ocr-how-to-run-and-fine-tune)).

**GPU sizing.** DeepSeek-OCR is ~3B params — it fits comfortably in **16 GB**
(e.g. an RTX 5080 or RTX 2000 Ada), single GPU, no tensor-parallel. With two
GPUs, pin the OCR server to one and leave the other for the app (docling /
embeddings) to avoid contention, e.g. set `device_ids: ['0']` on `deepseek-ocr`
and `['1']` on `booktutor` in `docker-compose.yaml` (replacing `count: all`), or
export `CUDA_VISIBLE_DEVICES` per service. Drop the `deploy.resources` block
entirely to run CPU-only (much slower).

---

## Project layout

```
src/booktutor/
├── config.py        # Settings from env / .env (pydantic-settings)
├── loaders.py       # make_loader(): docling (easyocr/tesseract) or VLM (DeepSeek-OCR)
├── factories.py     # make_llm() / make_embeddings()  (openai or local backend)
├── vectorstore.py   # FAISS collections: build / load / list
├── rag.py           # history-aware retrieval chain (LCEL)
└── cli.py           # ingest / chat / list
tests/               # config, paths, chunking
```

## Requirements

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/) (recommended) — or Docker
- A chat LLM endpoint (OpenAI-compatible); embeddings via an endpoint **or**
  the built-in local backend (`EMBEDDING_BACKEND=local`)
