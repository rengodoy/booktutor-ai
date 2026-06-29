"""Process view — live processing (mock)."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import ProgressBar, RichLog, Static

# (name, total, done, status-markup, color)
_ENGINES = [
    ("Tesseract", 12, 12, "12/12 ✓", "#6cc18f"),
    ("EasyOCR", 12, 8, "8/12 ⠹", "#4cc9b0"),
    ("DeepSeek-OCR", 12, 11, "11/12", "#4cc9b0"),
    ("Vision-LLM", 12, 0, "waiting", "#6a7488"),
]

_LOG = [
    "[#5a6273]14:31:38[/] [#6a7488]tesseract[/]   page 12/12 [#6cc18f]✓[/]",
    "[#5a6273]14:31:40[/] [#6a7488]easyocr[/]     page 8/12",
    "[#5a6273]14:31:41[/] [#e0b04a]warn[/]        page 9 divergence on currency token",
    "[#5a6273]14:31:42[/] [#4cc9b0]deepseek[/]    page 11/12",
    "[#5a6273]14:31:43[/] [#6a7488]$ glyph run --all --merge vision[/][#4cc9b0]█[/]",
]


class ProcessView(Vertical):
    def compose(self):
        overall = Vertical(id="overall", classes="panel")
        overall.border_title = "OVERALL · PROGRESSO GERAL"
        with overall:
            yield ProgressBar(total=64, show_eta=False, id="overall-bar")
            yield Static(
                "[$text-dim]pages[/] [$text-bright]41/64[/]    "
                "[$text-dim]elapsed[/] [$text-bright]02:18[/]    "
                "[$text-dim]eta[/] [$warning]00:09[/]    "
                "[$text-dim]throughput[/] [$text-bright]3.2 pg/s[/]",
                markup=True,
                id="overall-stats",
            )

        par = Vertical(id="parallel", classes="panel")
        par.border_title = "PARALLEL ENGINES · MOTORES EM PARALELO"
        with par:
            for name, total, done, status, color in _ENGINES:
                row = Horizontal(classes="eng-row")
                with row:
                    yield Static(name, classes="eng-name")
                    bar = ProgressBar(
                        total=total, show_eta=False, show_percentage=False
                    )
                    bar.advance(done)
                    yield bar
                    yield Static(
                        f"[{color}]{status}[/]", markup=True, classes="eng-status"
                    )

        log = Vertical(id="proc-log", classes="panel")
        log.border_title = "LIVE LOG · REGISTRO"
        with log:
            yield RichLog(id="proc-richlog", markup=True, highlight=False, wrap=True)

    def on_mount(self) -> None:
        self.query_one("#overall-bar", ProgressBar).advance(41)
        rlog = self.query_one("#proc-richlog", RichLog)
        for line in _LOG:
            rlog.write(line)

    # --- live run (called from the OCR worker via call_from_thread) --------
    def start_run(self, total: int, engine: str) -> None:
        self.query_one("#overall-bar", ProgressBar).update(
            total=max(total, 1), progress=0
        )
        self.query_one("#overall-stats", Static).update(
            f"[$text-dim]files[/] [$text-bright]0/{total}[/]    "
            f"[$text-dim]engine[/] [$accent]{engine}[/]"
        )
        self.query_one("#proc-richlog", RichLog).clear()

    def log_line(self, text: str) -> None:
        self.query_one("#proc-richlog", RichLog).write(text)

    def finish_file(self, done: int, name: str, chars: int) -> None:
        bar = self.query_one("#overall-bar", ProgressBar)
        bar.update(progress=done)
        total = bar.total or done
        self.query_one("#overall-stats", Static).update(
            f"[$text-dim]files[/] [$text-bright]{done}/{int(total)}[/]"
        )
        self.query_one("#proc-richlog", RichLog).write(
            f"[#6cc18f]✓[/] {name} [#6a7488]({chars:,} chars)[/]"
        )
