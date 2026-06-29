# Brief de design — TUI do "glyph" (terminal UI, OCR adaptativo)

Gere o design de uma **TUI de terminal** (não web app) para a ferramenta `glyph`.
Entregue **mockups anotados de cada tela nos 2 temas + uma folha de componentes**.

## Medium (importante)
Interface de **terminal monospace**, construída com **Textual (Python)**. Estética
autêntica de terminal: fonte mono, células de largura fixa (~120 colunas), bordas
com box-drawing (`─ │ ┌ ┐ └ ┘ ├ ┤`), barras com blocos (`█ ▓ ▒ ░`), títulos de
painel embutidos na borda (estilo `border_title`). Se renderizar como artifact
HTML/SVG, **simule um terminal** (fundo sólido, grid mono, sem sombras/gradientes
de web, sem ícones raster — só glyphs unicode). Cor só via tokens de tema.

## O produto (contexto pra UX)
`glyph` faz OCR de PDF → Markdown com **um comando adaptativo**. Por página: começa
no engine mais simples; um **Vision-LLM juiz** lê a imagem + o texto candidato,
devolve markdown + uma **confiança 0..1**, e **escala** o ladder de engines só
quando a confiança é baixa — avisando o usuário a cada passo. Engines pesados sobem
como **serviços em container sob demanda** (podem levar minutos pra carregar o
modelo). Ladder default: `easyocr → tesseract → easyocr+tesseract → +deepseek2`.

**North star do design:** tornar o STATUS de processamento óbvio e tranquilizador —
o usuário precisa ver que está processando, em que página/engine está, quando
escala, e quando um serviço está subindo (pode demorar). Barras de progresso e
spinners são protagonistas.

## Arquitetura de informação
7 views + footer de atalhos. **Dois layouts alternáveis** (tecla `b`):
- **Layout A — sidebar**: navegação vertical à esquerda + conteúdo à direita.
- **Layout B — top-tabs**: abas no topo + dashboard focado em documento.

Views:
1. **Dashboard** — visão geral do pipeline (fila, engines, atividade, stats).
2. **Input** — seleção de PDFs (árvore de arquivos, contagem de páginas).
3. **Engines** — config do ladder + Vision-LLM (cards por engine, estratégia/tiers).
4. **Process** — *tela herói*, processamento ao vivo (detalhe abaixo).
5. **Compare** — candidatos lado-a-lado por engine + resultado reconciliado + confiança.
6. **Markdown** — preview (source + render) do `.md` extraído.
7. **Export** — destino de saída + resumo.

Footer fixo de keybindings (labels **bilíngues PT·EN**): `r Run·Rodar`,
`e Export·Exportar`, `b Layout`, `t Theme·Tema`, `l Lang`, `? Help·Ajuda`, `q Quit·Sair`.

## Tela herói: Process (detalhar bem)
Componentes empilhados:
- **Barra de progresso geral (páginas)**: `pages 23/64` + `elapsed 02:18` +
  `eta 00:41` + `throughput 3.2 pg/s`. Determinada.
- **Barras por engine (uma por tier do ladder)**: linha `nome · barra · status`.
  Estados: waiting / running (spinner) / done ✓ / overruled ✗.
- **Painel de status de serviço (on-demand)**: quando um engine pesado sobe, mostrar
  `deepseek2 · subindo modelo ▓▓▓░░ 60%` ou, sem %, **spinner indeterminado +
  elapsed** (`loading DeepSeek-OCR-2… 0:47`). É o que comunica "pode demorar".
- **Log ao vivo de escalada**: linhas timestamped, ex:
  `14:31:40 easyocr     page 2/64  confidence 0.61 < 0.85 — escalating to tesseract`
  `14:31:42 tesseract   page 2/64  confidence 0.89 ✓`
- **Medidor de confiança** da página/documento (barra + número, ex `0.91`).

## Estados que o design DEVE representar
O orquestrador emite eventos (contrato `ProgressReporter`). Mapeie cada um a um
estado visual — inclua **determinado (barra %)** e **indeterminado (spinner)**:

| Evento | Estado visual |
|---|---|
| run_start(total_pages, tiers) | barra geral zerada; ladder desenhado |
| page_start(n/total) | página atual destacada |
| service_starting(svc) | card de serviço "starting…" + spinner |
| service_progress(svc, frac\|null, stage) | barra % se `frac`; senão spinner + elapsed |
| service_ready(svc, elapsed) | card vira "ready ✓" |
| engine_start(page, engine) | linha do engine em running (spinner) |
| engine_progress(page, engine, frac\|null) | sub-barra % ou spinner |
| engine_done(page, engine, chars) | linha do engine done |
| reconcile(page, tier, conf, accepted, next) | linha de log + confiança; se !accepted, "escalating to {next}" |
| page_done(page, conf, tier) | barra geral avança; confiança atualiza |
| run_done(pages, elapsed, out) | estado final / resumo |
| message(level, text) | linha de log (info/warn/error com cor) |

Telas vazias/idle também: "no PDF selected", "waiting to run", erro de serviço
("deepseek2 failed to start — skipped").

## Direção visual — 2 temas
Mono, denso, alto contraste. Tokens de cor (ajuste por tema):
- **Midnight** (default, dark frio): fundo azul-escuro; accent **teal `#4cc9b0`**;
  success **green `#6cc18f`**; warn **amber `#e0b04a`**; error **red `#e06c6c`**;
  reconcile/merge **purple `#a98ad0`**; dim **`#6a7488`**; texto bright quase branco.
- **Ember** (warm): mesma estrutura, paleta quente (âmbar/laranja/terracota), accent
  quente, mantendo os papéis (success/warn/error/dim) legíveis.
Use os tokens semanticamente (success/warn/error/accent/dim/bright), não cores cruas,
pra os dois temas baterem. Barras: trilho `░`/dim, preenchido `█`/accent.

## Inventário de componentes (folha à parte)
ProgressBar (determinada + indeterminada/spinner), status pill (waiting/running/
ready/failed), engine row (nome+barra+status+confiança), service card (nome+stage+
barra/spinner+elapsed), log pane (linhas timestamped coloridas), confidence meter,
sidebar nav item (ativo/inativo), top-tab, key-binding footer, panel com border_title
bilíngue.

## Constraints
- Largura alvo ~120 colunas; tudo em células de terminal.
- Sem imagens/ícones raster; só unicode + box-drawing.
- Cor só via tokens de tema (2 temas devem funcionar com o mesmo layout).
- Labels de ação bilíngues `PT · EN`.

## Entregável
1. Mockup anotado de **cada uma das 7 views** (priorize **Process**), em **Midnight**.
2. As 2–3 views principais (Dashboard, Process, Compare) também em **Ember**.
3. **Folha de componentes** com os estados (determinado/indeterminado, waiting/
   running/ready/failed, confiança alta/baixa).
4. Anote em cada tela qual **evento** alimenta cada elemento (use a tabela acima).
