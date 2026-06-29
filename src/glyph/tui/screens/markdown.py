"""Markdown view — source + rendered preview of the generated .md.

Shows mock content until a run finishes, then :meth:`populate` swaps in the real
results (one tab per file).
"""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Markdown, Static, Tabs

_MOCK_NAME = "exemplo.md"
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


def _stats(md: str) -> str:
    words = len(md.split())
    headings = sum(1 for ln in md.splitlines() if ln.lstrip().startswith("#"))
    tables = md.count("\n| ")
    return (
        f"[$text-dim]words[/] [$text-bright]{words:,}[/]   "
        f"[$text-dim]headings[/] [$text-bright]{headings}[/]   "
        f"[$text-dim]tables[/] [$text-bright]{tables}[/]"
    )


class MarkdownView(Vertical):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._results: dict[str, str] = {_MOCK_NAME: _MD}

    def compose(self):
        yield Static(_stats(_MD), markup=True, id="md-stats")
        yield Tabs(_MOCK_NAME, id="md-tabs")
        with Horizontal(id="md-split"):
            src = Vertical(classes="panel", id="md-source")
            src.border_title = "SOURCE · FONTE"
            with src:
                # markup=False: raw markdown can contain [..] that isn't markup.
                yield Static(_MD, markup=False, id="md-src-body")
            rend = Vertical(classes="panel", id="md-rendered")
            rend.border_title = "RENDERED · RENDERIZADO"
            with rend:
                yield Markdown(_MD, id="md-rendered-body")

    def populate(self, results: dict[str, str]) -> None:
        self._results = dict(results) or {_MOCK_NAME: _MD}
        tabs = self.query_one("#md-tabs", Tabs)
        tabs.clear()
        for name in self._results:
            tabs.add_tab(name)
        first = next(iter(self._results))
        self._show(first)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        self._show(str(event.tab.label))

    def _show(self, name: str) -> None:
        md = self._results.get(name, "")
        self.query_one("#md-stats", Static).update(_stats(md))
        self.query_one("#md-src-body", Static).update(md)
        self.query_one("#md-rendered-body", Markdown).update(md)
