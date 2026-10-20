"""Theme pins for the namesake "blueprint" palette (v1.2.7).

The palette constants live in ``gui/theme.py`` — the single source of
truth. These tests lock the exact locked values from the fleet
namesake design package, the fleet danger red, the alias wiring the
window code relies on, and the WCAG contrast of every text/background
pair the stylesheet renders (≥4.5:1, computed with the standard
relative-luminance formula). They also scan the GUI sources so no
retired pre-palette color can creep back in as a literal.
"""

import colorsys
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gui import theme

GUI_DIR = os.path.join(os.path.dirname(__file__), "..", "gui")

# The locked namesake set (PALETTES.md, owner order 2026-10-20).
LOCKED = {
    "BG": "#06090c",
    "PANEL": "#0b1116",
    "PANEL_BORDER": "#20303c",
    "TEXT": "#e4edf2",
    "TEXT_FAINT": "#8fa5b0",
    "PRIMARY": "#33b5e8",
    "PRIMARY_DARK_TEXT": "#03131b",
    "ACCENT": "#8fd4f2",
    "INPUT_BG": "#080d11",
    "DISABLED_TEXT": "#76909d",
    "RED": "#b03a2e",
    "RED_TEXT": "#ffffff",
    "SUCCESS": "#4ade80",
    "WARNING": "#fbbf24",
    "ERROR": "#f87171",
}

# Colors retired by the palette pass — none may reappear in gui/.
RETIRED = [
    "#0f141b",
    "#161d27",
    "#1c2431",
    "#2a3444",
    "#e8eef5",
    "#93a1b5",
    "#38bdf8",
    "#0e7490",
    "#232d3d",
    "#5b6a7e",
    "#06202b",
    "#7dd3fc",
    "#274b5c",
    "#7b8fa3",
    "#5c2b2b",
    "#3a1d1d",
    "#131924",
    "#1e3a4c",
    "#33506a",
    "#12222e",
    "#0b0f15",
]


def _lum(hex_color):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))

    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _ratio(fg, bg):
    lo, hi = sorted((_lum(fg), _lum(bg)))
    return (hi + 0.05) / (lo + 0.05)


# Every text/background pair the stylesheet actually renders.
PAIRS = []
for _fg in ("TEXT", "TEXT_FAINT", "PRIMARY", "ACCENT"):
    for _bg in ("BG", "PANEL", "INPUT_BG"):
        PAIRS.append((_fg, _bg))
PAIRS += [
    ("TEXT", "PANEL_BORDER"),  # selections, pressed fills
    ("PRIMARY_DARK_TEXT", "PRIMARY"),  # primary button label
    ("RED_TEXT", "RED"),  # danger button hover fill
    ("DISABLED_TEXT", "BG"),
    ("DISABLED_TEXT", "PANEL"),
    ("DISABLED_TEXT", "INPUT_BG"),  # disabled buttons + primary button
    ("SUCCESS", "PANEL"),
    ("SUCCESS", "INPUT_BG"),
    ("WARNING", "PANEL"),
    ("WARNING", "INPUT_BG"),
    ("ERROR", "PANEL"),
    ("ERROR", "INPUT_BG"),  # log lines + danger button label
]


def test_constants_are_the_locked_values():
    for name, expected in LOCKED.items():
        assert getattr(theme, name) == expected, name


def test_alias_wiring():
    assert theme.PANEL_LIGHT == theme.INPUT_BG
    assert theme.BORDER == theme.PANEL_BORDER
    assert theme.TEXT_DIM == theme.TEXT_FAINT
    assert theme.ACCENT_DARK == theme.PANEL_BORDER


def test_every_rendered_pair_meets_wcag_aa():
    for fg_name, bg_name in PAIRS:
        fg, bg = getattr(theme, fg_name), getattr(theme, bg_name)
        assert _ratio(fg, bg) >= 4.5, f"{fg_name} on {bg_name}: {_ratio(fg, bg):.2f}"


def test_worst_pair_is_disabled_on_panel():
    # The design package's stated worst pair, 5.65:1.
    assert abs(_ratio(theme.DISABLED_TEXT, theme.PANEL) - 5.65) < 0.05


def test_no_purple_anywhere_in_the_palette():
    for name in LOCKED:
        value = getattr(theme, name)
        h = value.lstrip("#")
        r, g, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
        hue, _lightness, sat = colorsys.rgb_to_hls(r, g, b)
        if sat > 0.15:
            assert not (0.72 < hue < 0.92), f"{name} {value} is in the purple band"


def test_no_retired_color_literals_in_gui_sources():
    for fname in os.listdir(GUI_DIR):
        if not fname.endswith(".py"):
            continue
        with open(os.path.join(GUI_DIR, fname), encoding="utf-8") as fh:
            src = fh.read().lower()
        for retired in RETIRED:
            assert retired not in src, f"{retired} reappeared in gui/{fname}"


def test_color_literals_live_only_in_theme_module():
    hex_re = re.compile(r"#[0-9a-fA-F]{6}\b")
    with open(os.path.join(GUI_DIR, "main_window.py"), encoding="utf-8") as fh:
        src = fh.read()
    assert not hex_re.search(src), "main_window.py must take every color from gui.theme"
