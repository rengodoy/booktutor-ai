"""Input view — file selection (mock browse of the current dir)."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import DirectoryTree, Static

_SELECTED = (
    "[$text-bright]relatorio_anual_pt.pdf[/]  [$text-dim]PT · 12p[/]\n"
    "[$text-bright]invoice_en.png[/]          [$text-dim]EN · 1p[/]\n"
    "[$text-bright]manual_misc.pdf[/]         [$text-dim]PT·EN · 48p[/]\n"
    "[$text-bright]recibo_scan.tiff[/]        [$text-dim]AUTO · 3p[/]\n\n"
    "[$accent]4 files · 64 pages[/]"
)

_DETECTED = (
    "[$text-dim]language[/]    [$text-bright]auto (por+eng)[/]\n"
    "[$text-dim]resolution[/]  [$text-bright]300 dpi[/]\n"
    "[$text-dim]deskew[/]      [$success]on[/]\n"
    "[$text-dim]preprocess[/]  [$text-bright]denoise · binarize[/]"
)


class InputView(Horizontal):
    def compose(self):
        browse = Vertical(classes="panel", id="browse")
        browse.border_title = "BROWSE · NAVEGAR"
        with browse:
            yield Static("[$text-dim]📂 ~/scans / 2024[/]", markup=True, id="crumb")
            yield DirectoryTree(".", id="file-tree")
            yield Static(
                "[$text-faint]drag & drop files here · or paste a path with [/]"
                "[$accent]o[/]",
                markup=True,
                id="browse-foot",
            )
        right = Vertical(id="input-right")
        with right:
            sel = Vertical(classes="panel", id="selected")
            sel.border_title = "SELECTED · SELECIONADOS 4"
            with sel:
                yield Static(_SELECTED, markup=True)
            det = Vertical(classes="panel", id="detected")
            det.border_title = "DETECTED · DETECTADO"
            with det:
                yield Static(_DETECTED, markup=True)
            thumb = Vertical(classes="panel", id="thumb")
            thumb.border_title = "PREVIEW"
            with thumb:
                yield Static("", id="thumb-img")
