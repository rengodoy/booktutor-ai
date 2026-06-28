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
- [ ] Avaliar otimizar o OCR com um Vision-LLM (ex: Qwen3-VL) que reconcilia a saída
      de múltiplas engines e monta o melhor Markdown possível
- [ ] Usar DeepSeek-OCR v2
- [ ] Atualizar todos os pacotes usados.

## 3. TUI (glyph)
- [ ] Implementar a TUI descrita em `design_handoff_glyph_tui/README.md` usando Textual
  - 9 telas: Dashboard (Midnight / Ember / Layout B), Input, Engines, Process,
    Compare, Markdown, Export
  - referência visual: `design_handoff_glyph_tui/glyph TUI.dc.html` + `screenshots/`

## Questões em aberto
- Renomear o projeto de `booktutor` para `glyph`? (o design já usa o nome `glyph`)
