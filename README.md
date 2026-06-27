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

Both the LLM and the embeddings speak the **OpenAI API standard**, so you can
point them at any compatible endpoint — OpenAI, Azure OpenAI, vLLM, LM Studio,
Ollama, llama.cpp, etc. Nothing is hardcoded to a single provider.

## Requirements

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/) (recommended) or pip
- An OpenAI-compatible endpoint for both chat and embeddings

## Setup

```bash
uv sync                 # install dependencies
cp .env.example .env    # then edit .env with your endpoint/model/key
```

Minimal `.env` for a local LM Studio / Ollama server:

```dotenv
LLM_API_BASE=http://localhost:1234/v1
LLM_API_KEY=not-needed
LLM_MODEL=your-local-model
EMBEDDING_MODEL=your-embedding-model
```

…or for hosted OpenAI:

```dotenv
LLM_API_BASE=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small
```

See [`.env.example`](.env.example) for every option (chunking, retrieval depth,
OCR, separate embedding endpoint, …).

## Usage

```bash
# 1. Ingest one or more PDFs into a named collection
uv run booktutor ingest path/to/textbook.pdf --collection physics

# 2. Chat with it
uv run booktutor chat --collection physics

# Or do both at once (ingests if the collection doesn't exist yet)
uv run booktutor chat path/to/textbook.pdf

# List what you've already indexed
uv run booktutor list

# Show the retrieved source chunks alongside each answer
uv run booktutor chat --collection physics --show-sources
```

Indexes are cached under `INDEX_DIR` (default `indexes/`), so a book is only
processed once. You can also run it as a module: `uv run python -m booktutor ...`.

## Project layout

```
src/booktutor/
├── config.py        # Settings from env / .env (pydantic-settings)
├── loaders.py       # DoclingBookLoader (PDF -> markdown, OCR)
├── factories.py     # make_llm() / make_embeddings()  — OpenAI-compatible
├── vectorstore.py   # FAISS collections: build / load / list
├── rag.py           # history-aware retrieval chain (LCEL)
└── cli.py           # ingest / chat / list
tests/               # config, paths, chunking
```

## Development

```bash
uv run pytest        # run the test suite
uv run ruff check    # lint
```

## Docker

```bash
docker compose run --rm booktutor booktutor list
```

The image installs the Tesseract OCR language packs (`por`, `eng`) and the
project. Mount your PDFs and pass an `.env` (see `docker-compose.yaml`).
