"""glyph — the Textual app: common frame (header, sidebar, footer) + views.

Canonical layout from the design handoff: a custom header bar, a left PIPELINE
nav sidebar, a content area that swaps views, and a footer of key bindings.
Two themes (Midnight default / Ember) toggle at runtime with ``t``.
"""

from __future__ import annotations

from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    ContentSwitcher,
    Footer,
    Label,
    ListItem,
    ListView,
    Static,
)

from booktutor.tui.screens.compare import CompareView
from booktutor.tui.screens.dashboard import DashboardView
from booktutor.tui.screens.engines import EnginesView
from booktutor.tui.screens.export import ExportView
from booktutor.tui.screens.input import InputView
from booktutor.tui.screens.markdown import MarkdownView
from booktutor.tui.screens.process import ProcessView
from booktutor.tui.themes import THEMES

# (view id, sidebar label, header subtitle)
NAV = [
    ("dashboard", "Dashboard", "pipeline overview"),
    ("input", "Input · Entrada", "select files"),
    ("engines", "Engines · Motores", "configure OCR"),
    ("process", "Process · Processar", "live processing"),
    ("compare", "Compare · Comparar", "engine results"),
    ("markdown", "Markdown", "preview"),
    ("export", "Export · Exportar", "save output"),
]
_SUBTITLE = {key: sub for key, _, sub in NAV}


class GlyphHeader(Horizontal):
    """Top chrome: brand + screen subtitle (left), LANG/status/clock (right)."""

    def compose(self) -> ComposeResult:
        yield Static("◆ glyph", classes="brand")
        yield Static("│", classes="sep")
        yield Static("pipeline overview", id="subtitle", classes="subtitle")
        yield Static("", classes="spacer")
        yield Static("LANG  PT · EN", classes="pill")
        yield Static("● running", classes="status")
        yield Static("--:--", id="clock", classes="clock")

    def on_mount(self) -> None:
        self._tick()
        self.set_interval(10, self._tick)

    def _tick(self) -> None:
        self.query_one("#clock", Static).update(datetime.now().strftime("%H:%M"))


class GlyphApp(App):
    CSS_PATH = "glyph.tcss"
    TITLE = "glyph"

    BINDINGS = [
        ("t", "toggle_theme", "Theme · Tema"),
        ("l", "toggle_lang", "Lang"),
        ("question_mark", "help", "Help · Ajuda"),
        ("q", "quit", "Quit · Sair"),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Register + activate before CSS parses, so its custom variables
        # ($text-dim, $glyph-border, ...) resolve.
        for theme in THEMES:
            self.register_theme(theme)
        self.theme = "glyph-midnight"

    def compose(self) -> ComposeResult:
        yield GlyphHeader(id="glyph-header")
        with Horizontal(id="body"):
            nav = Vertical(id="nav")
            nav.border_title = "PIPELINE · FLUXO"
            with nav:
                yield ListView(
                    *(ListItem(Label(lbl), id=f"nav-{key}") for key, lbl, _ in NAV),
                    id="nav-list",
                )
                yield Static(
                    "[$text-faint]queue · fila 3[/]\n"
                    "[$text-faint]done · prontos 18[/]\n"
                    "[$text-faint]gpu cuda:0[/]",
                    id="nav-foot",
                    markup=True,
                )
            with ContentSwitcher(initial="dashboard", id="content"):
                yield DashboardView(id="dashboard")
                yield InputView(id="input")
                yield EnginesView(id="engines")
                yield ProcessView(id="process")
                yield CompareView(id="compare")
                yield MarkdownView(id="markdown")
                yield ExportView(id="export")
        yield Footer()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None or event.item.id is None:
            return
        key = event.item.id.removeprefix("nav-")
        self.query_one("#content", ContentSwitcher).current = key
        self.query_one("#subtitle", Static).update(_SUBTITLE.get(key, ""))

    def action_toggle_theme(self) -> None:
        self.theme = (
            "glyph-ember" if self.theme == "glyph-midnight" else "glyph-midnight"
        )

    def action_toggle_lang(self) -> None:
        # Labels are bilingual already; a real toggle lands with i18n later.
        self.bell()

    def action_help(self) -> None:
        self.bell()


def main() -> None:
    GlyphApp().run()


if __name__ == "__main__":
    main()
