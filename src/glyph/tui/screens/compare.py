"""Compare view — same region read by 3 engines + the merge (mock)."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Static

# (engine, tag-markup, conf-bar, ocr-text-markup)
_COLS = [
    (
        "Tesseract",
        "[#6cc18f]✓ agrees[/]",
        "[#6cc18f]█████████[/] 0.92",
        "Total a pagar  [#6cc18f]R$ 1.284,50[/]",
    ),
    (
        "EasyOCR",
        "[#e06c6c]✗ overruled[/]",
        "[#4cc9b0]███████░░[/] 0.88",
        "Total a pagar  R$ 1.284,5[#e06c6c on #3a2020]O[/]",
    ),
    (
        "DeepSeek-OCR",
        "[#6cc18f]✓ agrees[/]",
        "[#6cc18f]█████████[/] 0.95",
        "Total a pagar  [#6cc18f]R$ 1.284,50[/]",
    ),
]

_MERGED = (
    "[$text-bright]| Total a pagar / Amount due | R$ 1.284,50 |[/]\n\n"
    "[$text-dim]EasyOCR read the cents as `5O` (letter O); 2/3 engines and the "
    "image agree on `50`. Reconstructed as a currency cell.[/]"
)

_CONF = (
    "[$text-dim]consensus[/]   [$text-bright]2/3[/]\n"
    "[$text-dim]merged conf[/] [$accent]0.97[/]\n"
    "[$text-dim]validation[/]  [$success]✓ currency[/]"
)


class CompareView(Vertical):
    def compose(self):
        yield Static(
            "[$text-dim]page 7 · region: table[/]      "
            "[$accent]◂[/] [$text-bright]region 3/11[/] [$accent]▸[/]",
            markup=True,
            id="compare-head",
        )
        with Horizontal(id="compare-cols"):
            for engine, tag, conf, text in _COLS:
                col = Vertical(classes="cmp-col panel")
                col.border_title = engine
                with col:
                    yield Static(tag, markup=True)
                    yield Static(conf, markup=True, classes="cmp-conf")
                    yield Static(text, markup=True, classes="cmp-text")
        merged = Vertical(id="merged", classes="panel accent")
        merged.border_title = "◆ MERGED · VISION-LLM RECONCILED"
        with merged:
            with Horizontal():
                yield Static(_MERGED, markup=True, id="merged-body")
                box = Vertical(id="conf-box", classes="panel")
                box.border_title = "CONFIDENCE"
                with box:
                    yield Static(_CONF, markup=True)
