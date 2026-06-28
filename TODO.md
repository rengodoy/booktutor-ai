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
      (conservador: segura torch/torchvision/transformers/docling via
      `[tool.uv] constraint-dependencies`; resto atualizado)
- [ ] (opcional) subir os floors `>=` no `pyproject.toml` pros novos resolvidos

### 2b. DeepSeek-OCR 2
- [x] Serving decidido: **transformers in-process** (`OCR_ENGINE=deepseek2`)
      — vLLM CUDA não suporta `DeepseekOCR2ForCausalLM` (issue #41468)
- [x] `DeepSeekOcr2Loader` (trust_remote_code), modelo configurável
      (default `deepseek-ai/DeepSeek-OCR-2`; alt `unsloth/DeepSeek-OCR-2`)
- [x] Prompt grounding + params (base_size 1024, image_size 768, crop_mode,
      attn_impl `eager` por padrão → roda sem flash-attn)
- [x] Deps: `transformers`, `einops`, `addict`, `easydict` (flash-attn opcional)
- [ ] **Validar end-to-end numa GPU** (download do modelo ~vários GB; conferir
      compat transformers 4.52 vs 4.46.3 do model card)

### 2c. Merge multi-engine via Vision-LLM
- [ ] Avaliar otimizar o OCR com um Vision-LLM (ex: Qwen3-VL) que reconcilia a saída
      de múltiplas engines e monta o melhor Markdown possível

## 3. TUI (glyph)
- [ ] Implementar a TUI descrita em `design_handoff_glyph_tui/README.md` usando Textual
  - 9 telas: Dashboard (Midnight / Ember / Layout B), Input, Engines, Process,
    Compare, Markdown, Export
  - referência visual: `design_handoff_glyph_tui/glyph TUI.dc.html` + `screenshots/`

## Questões em aberto
- Renomear o projeto de `booktutor` para `glyph`? (o design já usa o nome `glyph`)
