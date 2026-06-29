"""Input view — file selection (real: pick PDFs from the tree)."""

from __future__ import annotations

from pathlib import Path

from textual.containers import Horizontal, Vertical
from textual.widgets import DirectoryTree, Static

_DETECTED = (
    "[$text-dim]language[/]    [$text-bright]auto (por+eng)[/]\n"
    "[$text-dim]resolution[/]  [$text-bright]300 dpi[/]\n"
    "[$text-dim]deskew[/]      [$success]on[/]\n"
    "[$text-dim]preprocess[/]  [$text-bright]denoise · binarize[/]"
)


def _page_count(path: Path) -> int | None:
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        try:
            return len(pdf)
        finally:
            pdf.close()
    except Exception:
        return None


class InputView(Horizontal):
    def compose(self):
        browse = Vertical(classes="panel", id="browse")
        browse.border_title = "BROWSE · NAVEGAR"
        with browse:
            yield Static(
                "[$text-dim]📂 select PDFs (enter)[/]", markup=True, id="crumb"
            )
            yield DirectoryTree(".", id="file-tree")
            yield Static(
                "[$text-faint]enter a .pdf to (de)select · then press [/]"
                "[$accent]r[/][$text-faint] to run[/]",
                markup=True,
                id="browse-foot",
            )
        right = Vertical(id="input-right")
        with right:
            sel = Vertical(classes="panel", id="selected")
            sel.border_title = "SELECTED · SELECIONADOS"
            with sel:
                yield Static("[$text-dim](nenhum)[/]", markup=True, id="selected-body")
            det = Vertical(classes="panel", id="detected")
            det.border_title = "DETECTED · DETECTADO"
            with det:
                yield Static(_DETECTED, markup=True)
            thumb = Vertical(classes="panel", id="thumb")
            thumb.border_title = "PREVIEW"
            with thumb:
                yield Static("", id="thumb-img")

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        if event.path.suffix.lower() != ".pdf":
            self.app.notify("Only .pdf files can be selected.", severity="warning")
            return
        self.app.toggle_file(event.path)
        self.refresh_selected()

    def refresh_selected(self) -> None:
        paths = self.app.selected_paths
        sel = self.query_one("#selected-body", Static)
        title = self.query_one("#selected", Vertical)
        if not paths:
            sel.update("[$text-dim](nenhum)[/]")
            title.border_title = "SELECTED · SELECIONADOS"
            return
        lines = []
        total_pages = 0
        for p in paths:
            pages = _page_count(p)
            total_pages += pages or 0
            tag = (
                f"[$text-dim]{pages}p[/]" if pages is not None else "[$text-faint]?[/]"
            )
            lines.append(f"[$text-bright]{p.name}[/]  {tag}")
        lines.append(f"\n[$accent]{len(paths)} files · {total_pages} pages[/]")
        sel.update("\n".join(lines))
        title.border_title = f"SELECTED · SELECIONADOS {len(paths)}"
