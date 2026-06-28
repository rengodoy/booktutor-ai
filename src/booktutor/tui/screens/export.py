"""Export view — output destination, format, options, summary + CTA (mock)."""

from __future__ import annotations

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
            yield Input(value="~/out/markdown/", id="out-path")
            yield Input(value="{name}.{lang}.md", id="out-naming")

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
                yield Static(_SUMMARY, markup=True)
            cta = Vertical(id="export-cta")
            with cta:
                yield Button("⏎  Export · Exportar", variant="success", id="do-export")
                yield Static("[$text-dim]4 files → ~/out/markdown/[/]", markup=True)
