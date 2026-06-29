import pytest

pytest.importorskip("textual")  # TUI ships in the docling extra

from glyph.tui.app import NAV  # noqa: E402
from glyph.tui.themes import THEMES  # noqa: E402


def test_nav_structure():
    keys = [key for key, _, _ in NAV]
    assert keys[0] == "dashboard"
    assert keys == [
        "dashboard",
        "input",
        "engines",
        "process",
        "compare",
        "markdown",
        "export",
    ]


def test_themes_registered():
    assert {t.name for t in THEMES} == {"glyph-midnight", "glyph-ember"}
