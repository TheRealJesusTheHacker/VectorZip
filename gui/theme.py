"""VectorZip theme — the namesake "blueprint" palette.

VectorZip is named for vectors and precision; its face is the blueprint:
a graphite-slate drafting surface, blueprint cyan lines, pale-cyan fine
detail. Constants are the locked fleet namesake set (owner order
2026-10-20; design package PALETTES.md), contrast-proven with the fleet
WCAG formula over the pairs the stylesheet renders — every pair ≥4.5:1,
worst pair DISABLED_TEXT on PANEL at 5.65:1.

This module is the single source of truth for every color the GUI
renders; ``tests/test_gui_theme.py`` pins the values and the pairs.
No purple anywhere (owner's standing rule — the single exception in the
fleet is Beerus, and this is not Beerus). The danger red is the fleet
constant ``#b03a2e`` with white text, identical in every Sentinel tool;
it is a *fill* color — as small text on these dark surfaces it measures
3.32:1, so error *text* keeps the brighter signal red (``ERROR``),
exactly as the fleet's other tools document theirs.
"""

# --- Blueprint surfaces and lines (the locked namesake set) ----------------
BG = "#06090c"  # graphite-slate window surface
PANEL = "#0b1116"  # card / panel surface
PANEL_BORDER = "#20303c"  # fine blueprint line; also selection + pressed fills
TEXT = "#e4edf2"  # primary text
TEXT_FAINT = "#8fa5b0"  # secondary text
PRIMARY = "#33b5e8"  # blueprint cyan
PRIMARY_DARK_TEXT = "#03131b"  # text on PRIMARY fills
ACCENT = "#8fd4f2"  # pale blueprint (fine detail, hovers)
INPUT_BG = "#080d11"  # inset surface: inputs, log, raised-panel role
DISABLED_TEXT = "#76909d"

# --- Fleet danger (identical in every tool) ---------------------------------
RED = "#b03a2e"
RED_TEXT = "#ffffff"

# --- Signal colors (status/log semantics; unchanged by the palette) ---------
SUCCESS = "#4ade80"
WARNING = "#fbbf24"
ERROR = "#f87171"  # error TEXT only — fills use RED with RED_TEXT

# --- Role aliases the window code has always used ----------------------------
PANEL_LIGHT = INPUT_BG  # raised/inset panel surface (the spec's INPUT_BG)
BORDER = PANEL_BORDER
TEXT_DIM = TEXT_FAINT
ACCENT_DARK = PANEL_BORDER  # deep tone paired with PRIMARY (gradients, selections)

MONO = "Consolas, 'SF Mono', Menlo, monospace"
