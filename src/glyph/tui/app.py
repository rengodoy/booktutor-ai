"""glyph — the Textual app: common frame (header, sidebar, footer) + views.

Canonical layout from the design handoff: a custom header bar, a left PIPELINE
nav sidebar, a content area that swaps views, and a footer of key bindings.
Two themes (Midnight default / Ember) toggle at runtime with ``t``.

Wired to the real OCR pipeline: Input selects PDFs, Engines picks the engine,
``r`` runs extraction in a worker (the blocking OCR offloaded via
asyncio.to_thread; live progress on Process), the result shows on Markdown and
``e`` writes it from Export.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    ContentSwitcher,
    Footer,
    Label,
    ListItem,
    ListView,
    Static,
    Tab,
    Tabs,
)

from glyph.config import Settings
from glyph.loaders import make_loader
from glyph.tui.screens.compare import CompareView
from glyph.tui.screens.dashboard import DashboardView
from glyph.tui.screens.dashboard_b import DashboardBView
from glyph.tui.screens.engines import EnginesView
from glyph.tui.screens.export import ExportView
from glyph.tui.screens.input import InputView
from glyph.tui.screens.markdown import MarkdownView
from glyph.tui.screens.process import ProcessView
from glyph.tui.themes import THEMES

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
_INDEX = {key: i for i, (key, _, _) in enumerate(NAV)}


class GlyphHeader(Horizontal):
    """Top chrome: brand + screen subtitle (left), LANG/status/clock (right)."""

    def compose(self) -> ComposeResult:
        yield Static("◆ glyph", classes="brand")
        yield Static("│", classes="sep")
        yield Static("pipeline overview", id="subtitle", classes="subtitle")
        yield Static("", classes="spacer")
        yield Static("LANG  PT · EN", classes="pill")
        yield Static("● idle", id="run-status", classes="status")
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
        ("r", "run_ocr", "Run · Rodar"),
        ("e", "export", "Export · Exportar"),
        ("b", "toggle_layout", "Layout"),
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
        # pipeline state
        self.selected_paths: list[Path] = []
        self.ocr_engine: str = "easyocr"
        self.out_dir: str = "out/markdown"
        self.results: dict[str, str] = {}
        self.layout_mode: str = "sidebar"  # "sidebar" (canonical) | "topbar" (Layout B)

    def compose(self) -> ComposeResult:
        yield GlyphHeader(id="glyph-header")
        yield Tabs(
            *(Tab(lbl, id=f"tab-{key}") for key, lbl, _ in NAV),
            id="topnav",
        )
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
                yield DashboardBView(id="dashboard-b")
                yield InputView(id="input")
                yield EnginesView(id="engines")
                yield ProcessView(id="process")
                yield CompareView(id="compare")
                yield MarkdownView(id="markdown")
                yield ExportView(id="export")
        yield Footer()

    # --- navigation -------------------------------------------------------
    def _current_key(self) -> str:
        current = self.query_one("#content", ContentSwitcher).current or "dashboard"
        return "dashboard" if current == "dashboard-b" else current

    def show_view(self, key: str) -> None:
        # In Layout B the Dashboard renders the document-focused variant.
        target = (
            "dashboard-b"
            if (key == "dashboard" and self.layout_mode == "topbar")
            else key
        )
        content = self.query_one("#content", ContentSwitcher)
        if content.current != target:
            content.current = target
        self.query_one("#subtitle", Static).update(_SUBTITLE.get(key, ""))
        # keep both navs (sidebar + top-tabs) in sync; setters are guarded so the
        # change events they fire converge instead of looping.
        nav = self.query_one("#nav-list", ListView)
        if key in _INDEX and nav.index != _INDEX[key]:
            nav.index = _INDEX[key]
        tabs = self.query_one("#topnav", Tabs)
        if tabs.active != f"tab-{key}":
            tabs.active = f"tab-{key}"

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None or event.item.id is None:
            return
        self.show_view(event.item.id.removeprefix("nav-"))

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        if event.tabs.id != "topnav" or event.tab.id is None:
            return  # ignore other Tabs (e.g. the Markdown file tabs)
        self.show_view(event.tab.id.removeprefix("tab-"))

    def action_toggle_layout(self) -> None:
        self.layout_mode = "topbar" if self.layout_mode == "sidebar" else "sidebar"
        self.screen.set_class(self.layout_mode == "topbar", "layout-b")
        self.show_view(self._current_key())

    # --- pipeline state ---------------------------------------------------
    def toggle_file(self, path: Path) -> None:
        if path in self.selected_paths:
            self.selected_paths.remove(path)
        else:
            self.selected_paths.append(path)

    def set_engine(self, engine: str) -> None:
        self.ocr_engine = engine

    # --- run OCR ----------------------------------------------------------
    def action_run_ocr(self) -> None:
        if not self.selected_paths:
            self.notify("Select one or more PDFs first (Input).", severity="warning")
            self.show_view("input")
            return
        self.show_view("process")
        self.query_one("#run-status", Static).update("● running")
        self._ocr_worker()

    @work(exclusive=True)
    async def _ocr_worker(self) -> None:
        # Async worker: UI updates run on the event loop, the blocking OCR runs in
        # a thread via asyncio.to_thread (avoids the call_from_thread deadlock that
        # a thread=True worker hit under run_test).
        import asyncio

        settings = Settings().model_copy(update={"ocr_engine": self.ocr_engine})
        paths = list(self.selected_paths)
        proc = self.query_one(ProcessView)
        proc.start_run(len(paths), self.ocr_engine)

        results: dict[str, str] = {}
        for i, path in enumerate(paths, 1):
            proc.log_line(f"[#6a7488]{path.name}[/] — running")
            try:
                markdown = await asyncio.to_thread(
                    lambda p=path: make_loader(settings, str(p)).load()
                )
            except Exception as exc:  # noqa: BLE001
                markdown = ""
                proc.log_line(f"[#e06c6c]✗[/] {path.name}: {exc}")
            results[path.name] = markdown
            proc.finish_file(i, path.name, len(markdown))

        self.results = results
        self._on_ocr_done()

    def _on_ocr_done(self) -> None:
        self.query_one("#run-status", Static).update("● done")
        self.query_one(MarkdownView).populate(self.results)
        self.query_one(ExportView).set_summary(self.results, self.out_dir)
        self.show_view("markdown")

    # --- export -----------------------------------------------------------
    def action_export(self) -> None:
        if not self.results:
            self.notify("Nothing to export yet — run OCR first.", severity="warning")
            return
        out = self.query_one(ExportView).output_dir()
        out.mkdir(parents=True, exist_ok=True)
        for name, markdown in self.results.items():
            (out / name).write_text(markdown, encoding="utf-8")
        self.notify(f"Exported {len(self.results)} file(s) → {out}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "do-export":
            self.action_export()

    # --- misc actions -----------------------------------------------------
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
