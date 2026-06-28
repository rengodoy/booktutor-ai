"""Engines view — configure the OCR techniques (mock)."""

from __future__ import annotations

from textual.containers import Grid, Vertical
from textual.widgets import Static, Switch

# (id, title, subtitle, [(label, value)...], enabled, glow)
_CARDS = [
    (
        "tesseract",
        "Tesseract",
        "· OCR engine",
        [("lang", "por+eng"), ("psm", "3 · auto"), ("oem", "1 · LSTM")],
        True,
        False,
    ),
    (
        "easyocr",
        "EasyOCR",
        "· OCR engine",
        [("langs", "pt · en"), ("device", "cuda:0"), ("beam width", "5")],
        True,
        False,
    ),
    (
        "deepseek",
        "DeepSeek-OCR",
        "· OCR engine",
        [("model", "deepseek-ocr-2"), ("resolution", "1280 px"), ("batch", "4")],
        True,
        False,
    ),
    (
        "vision",
        "◆ Vision-LLM",
        "· merge & structure",
        [("model", "gemma-qat"), ("role", "reconcile → md"), ("temperature", "0.2")],
        True,
        True,
    ),
]

_STRATEGY = (
    "[$text-dim]scan[/] ──► ( [$text-bright]deskew · denoise · binarize[/] ) ──► "
    "{ [$text-bright]tesseract / easyocr / deepseek[/] } ──► "
    "[$accent]◆ vision-llm[/] ──► [$success]markdown.md[/]\n\n"
    "[$text-dim]3 motores de OCR rodam em paralelo · o modelo de visão reconcilia "
    "divergências, reconstrói tabelas e gera o Markdown final.[/]"
)


class EnginesView(Vertical):
    def compose(self):
        with Grid(id="engine-grid"):
            for cid, title, sub, params, enabled, glow in _CARDS:
                card = Vertical(classes="engine-card" + (" glow" if glow else ""))
                card.border_title = f"{title}  {sub}"
                with card:
                    yield Switch(value=enabled, id=f"sw-{cid}")
                    lines = "\n".join(
                        f"[$text-dim]{lbl}[/]  [$text-bright]{val}[/]"
                        for lbl, val in params
                    )
                    yield Static(lines, markup=True, classes="params")
        strat = Vertical(id="strategy", classes="panel")
        strat.border_title = "STRATEGY · ESTRATÉGIA"
        with strat:
            yield Static(_STRATEGY, markup=True)
