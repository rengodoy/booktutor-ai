"""Dashboard view — pipeline overview (Midnight canonical layout).

Mock data for now; wired to the real pipeline in a later step (TODO 3c).
"""

from __future__ import annotations

from rich.text import Text
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, RichLog, Static

# (name, pages, lang, status-label, status-color) — DataTable cells use Rich
# markup, not Textual $theme-vars, so status is a Rich Text with an explicit hex.
_DOCS = [
    ("relatorio_anual_pt.pdf", "12", "PT", "✓ done", "#6cc18f"),
    ("invoice_en.png", "1", "EN", "◐ 64%", "#4cc9b0"),
    ("manual_misc.pdf", "48", "PT·EN", "◐ 12%", "#4cc9b0"),
    ("recibo_scan.tiff", "3", "AUTO", "⏸ queued", "#5a6273"),
]

_ENGINES = [
    "[$success]●[/] Tesseract     [$success]████████░[/] 0.92",
    "[$success]●[/] EasyOCR       [$success]███████░░[/] 0.88",
    "[$success]●[/] DeepSeek-OCR  [$success]█████████[/] [$success]0.95[/]",
    "[$text-faint]──────────────────────────[/]",
    "[$accent]◆ Vision-LLM merge[/] [$text-dim]— organizing[/] [$accent]█████░░░░[/]",
]

# RichLog also uses Rich markup (no $theme-vars) -> hex colors.
_ACTIVITY = [
    "[#5a6273]14:31:38[/] [#6a7488]tesseract[/]  relatorio_anual_pt.pdf [#6cc18f]✓ done[/]",
    "[#5a6273]14:31:40[/] [#6a7488]easyocr  [/]  invoice_en.png page 1 [#4cc9b0]◐ 64%[/]",
    "[#5a6273]14:31:41[/] [#e0b04a]warn[/]       manual_misc.pdf mixed PT·EN layout",
    "[#5a6273]14:31:42[/] [#4cc9b0]vision-llm[/] reconciling table on page 7",
    "[#5a6273]14:31:42[/] [#6a7488]$ glyph run --all --merge vision[/][#4cc9b0]█[/]",
]

# (number, number-css-class, label)
_STATS = [
    ("24", "num", "docs · documentos"),
    ("0.91", "num-accent", "avg conf · confiança"),
    ("3.2", "num", "pg/s throughput · vazão"),
    ("18", "num-ok", ".md markdown ready"),
]


class DashboardView(Vertical):
    def compose(self):
        with Horizontal(id="dash-row1"):
            docs = Vertical(id="documents", classes="panel")
            docs.border_title = "DOCUMENTS · DOCUMENTOS"
            with docs:
                yield DataTable(id="docs-table", cursor_type="row", zebra_stripes=False)
            eng = Vertical(id="engines", classes="panel")
            eng.border_title = "ENGINES · MOTORES"
            with eng:
                yield Static("\n".join(_ENGINES), markup=True)

        act = Vertical(id="activity", classes="panel")
        act.border_title = "ACTIVITY · ATIVIDADE"
        with act:
            yield RichLog(id="activity-log", markup=True, highlight=False, wrap=True)

        with Horizontal(id="dash-stats"):
            for num, cls, lbl in _STATS:
                stat = Vertical(classes="stat")
                with stat:
                    yield Static(num, markup=True, classes=cls)
                    yield Static(lbl, markup=True, classes="lbl")

    def on_mount(self) -> None:
        table = self.query_one("#docs-table", DataTable)
        table.add_columns("NAME · NOME", "PAGES", "LANG", "STATUS")
        for name, pages, lang, status, color in _DOCS:
            table.add_row(name, pages, lang, Text(status, style=color))
        log = self.query_one("#activity-log", RichLog)
        for line in _ACTIVITY:
            log.write(line)
