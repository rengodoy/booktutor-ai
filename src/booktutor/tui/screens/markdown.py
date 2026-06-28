"""Markdown view — source + rendered preview of the generated .md (mock)."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Markdown, Static, Tabs

_FILES = ["relatorio_anual_pt.md", "invoice_en.md", "manual_misc.md"]

_MD = """# Relatório Anual 2024

## Resumo Executivo

O presente relatório consolida os **resultados** do exercício de 2024.

| Métrica | Valor |
| --- | --- |
| Receita | R$ 12,4M |
| Margem | 31% |

- Crescimento de 18% sobre 2023
- Expansão para 3 novos mercados
"""

# raw source with a little accent on markdown markers
_SRC = (
    "[$accent]# Relatório Anual 2024[/]\n\n"
    "[$accent]## Resumo Executivo[/]\n\n"
    "O presente relatório consolida os [$text-faint]**[/]resultados"
    "[$text-faint]**[/] do exercício de 2024.\n\n"
    "[$text-faint]| Métrica | Valor |[/]\n"
    "[$text-faint]| --- | --- |[/]\n"
    "| Receita | R$ 12,4M |\n"
    "| Margem | 31% |\n\n"
    "[$accent]-[/] Crescimento de 18% sobre 2023\n"
    "[$accent]-[/] Expansão para 3 novos mercados\n"
)


class MarkdownView(Vertical):
    def compose(self):
        yield Static(
            "[$text-dim]words[/] [$text-bright]3,412[/]   "
            "[$text-dim]headings[/] [$text-bright]14[/]   "
            "[$text-dim]tables[/] [$text-bright]5[/]",
            markup=True,
            id="md-stats",
        )
        yield Tabs(*_FILES, id="md-tabs")
        with Horizontal(id="md-split"):
            src = Vertical(classes="panel", id="md-source")
            src.border_title = "SOURCE · FONTE"
            with src:
                yield Static(_SRC, markup=True)
            rend = Vertical(classes="panel", id="md-rendered")
            rend.border_title = "RENDERED · RENDERIZADO"
            with rend:
                yield Markdown(_MD)
