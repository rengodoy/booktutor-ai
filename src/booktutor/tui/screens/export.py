"""Export view — output destination, format, options, summary + CTA (mock)."""

from __future__ import annotations

from pathlib import Path

from textual.containers import Grid, Horizontal, Vertical
from textual.widgets import Button, Input, RadioButton, RadioSet, Static, Switch

_OPTIONS = [
    ("YAML frontmatter", True),
    ("Embed images · imagens", True),
    ("Page anchors", False),
    ("Confidence notes", False),
]

_SUMMARY = (
    "[$text-dim]files[/]          [$text-bright]4 → 4 .md[/]\n"
    "[$text-dim]pages[/]          [$text-bright]64[/]\n"
    "[$text-dim]languages[/]      [$text-bright]por · eng[/]\n"
    "[$text-dim]avg confidence[/] [$accent]0.94[/]"
)


class ExportView(Vertical):
    def compose(self):
        out = Vertical(classes="panel", id="export-output")
        out.border_title = "OUTPUT · DESTINO"
        with out:
            yield Input(value="out/markdown/", id="out-path")
            yield Input(value="{name}.md", id="out-naming")

        with Grid(id="export-mid"):
            fmt = Vertical(classes="panel", id="export-format")
            fmt.border_title = "FORMAT · FORMATO"
            with fmt:
                yield RadioSet(
                    RadioButton("Markdown .md", value=True),
                    RadioButton("Markdown + PDF"),
                    RadioButton("Word .docx"),
                    RadioButton("Bundle .zip"),
                )
            opt = Vertical(classes="panel", id="export-options")
            opt.border_title = "OPTIONS · OPÇÕES"
            with opt:
                for label, on in _OPTIONS:
                    row = Horizontal(classes="opt-row")
                    with row:
                        yield Switch(value=on)
                        yield Static(label, markup=True, classes="opt-label")

        with Grid(id="export-bottom"):
            summ = Vertical(classes="panel", id="export-summary")
            summ.border_title = "SUMMARY · RESUMO"
            with summ:
                yield Static(_SUMMARY, markup=True, id="export-summary-body")
            cta = Vertical(id="export-cta")
            with cta:
                yield Button("⏎  Export · Exportar", variant="success", id="do-export")
                yield Static(
                    "[$text-dim]run OCR first[/]", markup=True, id="export-cta-note"
                )

    def output_dir(self) -> Path:
        return Path(self.query_one("#out-path", Input).value).expanduser()

    def set_summary(self, results: dict[str, str], out_dir: str) -> None:
        n = len(results)
        chars = sum(len(md) for md in results.values())
        self.query_one("#out-path", Input).value = out_dir
        self.query_one("#export-summary-body", Static).update(
            f"[$text-dim]files[/]   [$text-bright]{n} → {n} .md[/]\n"
            f"[$text-dim]chars[/]   [$text-bright]{chars:,}[/]\n"
            f"[$text-dim]output[/]  [$text-bright]{out_dir}[/]"
        )
        self.query_one("#export-cta-note", Static).update(
            f"[$text-dim]{n} files → {out_dir}[/]"
        )
