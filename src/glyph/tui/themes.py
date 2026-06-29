"""The two glyph themes (Midnight default, Ember) from the design handoff.

Design tokens map to Textual theme variables; the extra tokens (text-bright,
border, accent-dim, ...) ride along as custom ``variables`` and are referenced in
glyph.tcss as ``$text-bright`` etc. Toggle at runtime with ``t``.
"""

from __future__ import annotations

from textual.theme import Theme

MIDNIGHT = Theme(
    name="glyph-midnight",
    primary="#4cc9b0",
    secondary="#a98ad0",
    accent="#4cc9b0",
    foreground="#b8c1cf",
    background="#15171c",
    surface="#1a1d24",
    panel="#20242c",
    success="#6cc18f",
    warning="#e0b04a",
    error="#e06c6c",
    dark=True,
    variables={
        "text-bright": "#e6edf3",
        "text-dim": "#6a7488",
        "text-faint": "#5a6273",
        "glyph-border": "#2a2f3a",
        "glyph-border-dim": "#242a33",
        "accent-dim": "#2f7a6e",
        "violet": "#a98ad0",
        "panel-tint": "rgba(76,201,176,0.12)",
    },
)

EMBER = Theme(
    name="glyph-ember",
    primary="#e0954a",
    secondary="#a98ad0",
    accent="#e0954a",
    foreground="#cdbba9",
    background="#18130f",
    surface="#1d1813",
    panel="#241c14",
    success="#8fb26a",
    warning="#e0b04a",
    error="#d97a5f",
    dark=True,
    variables={
        "text-bright": "#ece0d3",
        "text-dim": "#8a7765",
        "text-faint": "#6f5f4e",
        "glyph-border": "#34291f",
        "glyph-border-dim": "#2a2018",
        "accent-dim": "#7a5226",
        "violet": "#a98ad0",
        "panel-tint": "rgba(224,149,74,0.12)",
    },
)

THEMES = [MIDNIGHT, EMBER]
