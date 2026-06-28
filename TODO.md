# TODO — book-processor → glyph

> Objetivo: isolar o app para fazer **só OCR** de alta qualidade (PDF → Markdown),
> rodando em container Docker, com uma TUI (Textual) por cima.
> Commitar a cada etapa concluída.

## 1. Escopo: virar ferramenta de OCR pura
- [x] Remover a parte de LLM / RAG / chat (responder perguntas sobre os livros)
  - `rag.py`, `vectorstore.py` e as partes de chat/embeddings de `cli.py` e `factories.py`
  - limpar settings de LLM / embeddings / chunking / retrieval em `config.py`
  - remover deps: `langchain*`, `faiss-cpu`, `sentence-transformers`
  - manter só o pipeline de OCR (`loaders.py`) e o comando `extract` (PDF → Markdown)
- [x] Focar execução em Docker (não na máquina host), para rodar em qualquer ambiente

## 2. Qualidade do OCR

### 2a. Atualizar dependências
- [x] `uv lock --upgrade` + `uv sync`; rodar `pytest` e `ruff check`
- [x] Upgrade agressivo do docling: 2.36.1 → 2.107.0 (docling-parse 4→7,
      `docling[easyocr,tesserocr]` extras; puxou transformers 4.52→5.12.1).
      Validado: imports, build de converter (easyocr/tesseract/none) e
      convert+export_to_markdown de 2 páginas reais OK.
- [x] Só o par GPU fica pinado (torch 2.7.1 / torchvision 0.22.1, cu128) —
      bump cego puxa torchvision cu130 e quebra no import.
- [ ] (opcional) subir os floors `>=` no `pyproject.toml` pros novos resolvidos

### 2b. DeepSeek-OCR 2
- [x] Serving decidido: **transformers in-process** (`OCR_ENGINE=deepseek2`)
      — vLLM CUDA não suporta `DeepseekOCR2ForCausalLM` (issue #41468)
- [x] `DeepSeekOcr2Loader` (trust_remote_code), modelo configurável
      (default `deepseek-ai/DeepSeek-OCR-2`; alt `unsloth/DeepSeek-OCR-2`)
- [x] Prompt grounding + params (base_size 1024, image_size 768, crop_mode,
      attn_impl `eager` por padrão → roda sem flash-attn)
- [x] Deps: `transformers`, `einops`, `addict`, `easydict` (flash-attn opcional)
- [x] **Validado end-to-end na GPU**: OCR-2 conflita com docling no mesmo venv
      (transformers <4.48 vs 5). Resolvido com extras mutuamente exclusivos
      (`booktutor[docling]` vs `booktutor[deepseek2]` via `[tool.uv] conflicts`)
      + imagem própria `Dockerfile.deepseek2` (serviço/profile `deepseek2`).
      Rodou em transformers 4.47.1: páginas reais → markdown limpo (PT, headings).
      Loader lê `result.mmd` (`save_results=True`).

### 2c. Merge multi-engine via Vision-LLM (escalonamento adaptativo)
Ideia: por página, escalonar fontes até a qualidade ser boa; um Vision-LLM
(ex: Qwen3-VL ~27B) avalia a qualidade e funde os pedaços. Ladder configurável:
`easyocr` → `tesseract` → `easyocr+tesseract` → `+deepseek2`. O reconciliador
sempre lê a imagem da página. `OCR_ENGINE=merge`. Endpoint reconciliador: a definir.
- [x] 2c-1: framework de escalonamento + juiz/merger Vision-LLM (tiers
      easyocr/tesseract), settings `MERGE_*`, ladder configurável, cache por
      página×engine, engine que falha vira candidato vazio. **Validado** com
      `qwen-27b` (llama-swap @127.0.0.1:8080): páginas reais → markdown PT limpo,
      conf 0.95; o reconciliador faz OCR da imagem mesmo com candidato vazio.
- [ ] 2c-2: expor deepseek2 como serviço HTTP de OCR (servidor no
      `Dockerfile.deepseek2`) — sem isso o tier deepseek2 não entra (conflito venv).
- [ ] 2c-3: adicionar o tier deepseek2 (via serviço) ao orquestrador + validar.

## 3. TUI (glyph)
- [ ] Implementar a TUI descrita em `design_handoff_glyph_tui/README.md` usando Textual
  - 9 telas: Dashboard (Midnight / Ember / Layout B), Input, Engines, Process,
    Compare, Markdown, Export
  - referência visual: `design_handoff_glyph_tui/glyph TUI.dc.html` + `screenshots/`

## Questões em aberto
- Renomear o projeto de `booktutor` para `glyph`? (o design já usa o nome `glyph`)
