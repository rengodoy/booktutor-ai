"""Dashboard — Layout B (frame 3): document-focused, top-tabs frame.

A hero NOW PROCESSING panel (big per-engine bars + thumbnail), a QUEUE panel,
a right column with ENGINES + STATS, and ACTIVITY at the bottom. Mock data.
"""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import ProgressBar, RichLog, Static

# (engine, total, done, color)
_BARS = [
    ("Tesseract", 12, 12, "#6cc18f"),
    ("EasyOCR", 12, 8, "#4cc9b0"),
    ("DeepSeek-OCR", 12, 11, "#4cc9b0"),
    ("Vision-LLM", 12, 4, "#a98ad0"),
]

_QUEUE = (
    "[$text-bright]manual_misc.pdf[/]   [$text-dim]48p · PT·EN[/]\n"
    "[$text-bright]recibo_scan.tiff[/]  [$text-dim]3p · AUTO[/]\n"
    "[$text-bright]notas_fiscais.pdf[/] [$text-dim]9p · PT[/]"
)

_ENGINES = (
    "[$success]●[/] Tesseract     [$success]████████░[/] 0.92\n"
    "[$success]●[/] EasyOCR       [$success]███████░░[/] 0.88\n"
    "[$success]●[/] DeepSeek-OCR  [$success]█████████[/] 0.95\n"
    "[$accent]◆ Vision-LLM[/]   [$accent]█████░░░░[/] merge"
)

_STATS = (
    "[$text-bright]24[/]   [$text-dim]docs · documentos[/]\n"
    "[$accent]0.91[/] [$text-dim]avg conf · confiança[/]\n"
    "[$text-bright]3.2[/]  [$text-dim]pg/s · vazão[/]\n"
    "[$success]18[/]   [$text-dim].md ready[/]"
)

_ACTIVITY = [
    "[#5a6273]14:31:40[/] [#6a7488]easyocr[/]     invoice_en.png page 1 [#4cc9b0]◐ 64%[/]",
    "[#5a6273]14:31:41[/] [#e0b04a]warn[/]        manual_misc.pdf mixed PT·EN",
    "[#5a6273]14:31:42[/] [#4cc9b0]vision-llm[/]  reconciling table on page 7",
]


class DashboardBView(Vertical):
    def compose(self):
        with Horizontal(id="dashb-top"):
            hero = Vertical(id="dashb-hero", classes="panel")
            hero.border_title = "NOW PROCESSING · PROCESSANDO"
            with hero:
                with Horizontal(id="dashb-bars-wrap"):
                    bars = Vertical(id="dashb-bars")
                    with bars:
                        for name, total, done, color in _BARS:
                            row = Horizontal(classes="eng-row")
                            with row:
                                yield Static(name, classes="eng-name")
                                bar = ProgressBar(
                                    total=total, show_eta=False, show_percentage=False
                                )
                                bar.advance(done)
                                yield bar
                                yield Static(
                                    f"[{color}]{done}/{total}[/]",
                                    markup=True,
                                    classes="eng-status",
                                )
                    yield Static("", id="dashb-thumb")
            right = Vertical(id="dashb-right")
            with right:
                eng = Vertical(classes="panel", id="dashb-engines")
                eng.border_title = "ENGINES · MOTORES"
                with eng:
                    yield Static(_ENGINES, markup=True)
                stats = Vertical(classes="panel", id="dashb-stats")
                stats.border_title = "STATS"
                with stats:
                    yield Static(_STATS, markup=True)

        queue = Vertical(classes="panel", id="dashb-queue")
        queue.border_title = "QUEUE · FILA 3"
        with queue:
            yield Static(_QUEUE, markup=True)

        act = Vertical(classes="panel", id="dashb-activity")
        act.border_title = "ACTIVITY · ATIVIDADE"
        with act:
            yield RichLog(id="dashb-log", markup=True, highlight=False, wrap=True)

    def on_mount(self) -> None:
        log = self.query_one("#dashb-log", RichLog)
        for line in _ACTIVITY:
            log.write(line)
