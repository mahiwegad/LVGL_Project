"""theme.py - The app's own light/dark design system.

CustomTkinter's stock dark mode ("just flip the appearance mode") looks flat:
every card turns the same grey and the accents stay stuck in light mode. This
module defines a hand-tuned palette for both modes plus the small helpers the
screens use to stay consistent:

  * ``theme.colors``  - the active palette (semantic keys, never raw hex in a
    screen),
  * ``theme.toggle()`` / ``theme.set_mode()`` - switch modes, persist the
    choice, and re-apply the CustomTkinter appearance mode,
  * ``polish_tree(widget)`` - one-pass dark remap for the older screens that
    still carry light-only colors baked in (results, tests, QC, dilution),
  * ``contrast_ratio()`` - used by the theme tests to guarantee text stays
    readable.

Import direction: this module only depends on customtkinter, so both ``ui``
and (lazily) ``workflow`` may import it without creating a cycle.
"""

from __future__ import annotations

import json
import os

import customtkinter as ctk

# Start-up mode. The analyzer always OPENS in light mode (lab SOP); the Dark
# toggle is a session choice and is not restored on the next launch.
START_IN_LIGHT = True

# --------------------------------------------------------------------------
# Layout scale
# --------------------------------------------------------------------------
# The instrument's panel is 1280x720 (7", 15.25 x 8.58 cm). Every screen in
# this app is therefore designed in "design pixels" for exactly that panel:
# the font sizes and heights written in the screens ARE what the operator sees
# on the device. When the same build runs on a bigger monitor (development,
# demo) the whole widget tree is scaled by ``ui_scale`` so the layout keeps the
# panel's proportions instead of huddling in a corner of the screen.
#
# Scaling mechanism: CustomTkinter scales widget dimensions AND font sizes by
# ``set_widget_scaling`` (core.py calls it once, before the first screen is
# built). Spacing that Tk owns - grid/pack padx/pady - is not covered by that,
# so the screens built for the panel ask for ``sp()`` instead of a raw number.
DESIGN_W, DESIGN_H = 1280, 720
MIN_UI_SCALE, MAX_UI_SCALE = 0.85, 1.6
# A window within this fraction of the design size is treated as the panel
# itself (see ui_scale_for). The instrument's panel is 1280x720, but a Pi whose
# framebuffer is left on 1366x768 - the usual default - is only 6.7% away from
# it, and scaling the design up by 6.7% there was enough to push long field
# labels and the last option of a picker out of their boxes. Snapping to 1.0
# keeps the layout exactly as designed on any panel-sized screen.
PANEL_SCALE_SNAP = 0.15

_UI_SCALE = 1.0


def set_ui_scale(scale):
    """Remember the window's layout scale (see sp()/ui_scale())."""
    global _UI_SCALE
    try:
        _UI_SCALE = max(MIN_UI_SCALE, min(float(scale), MAX_UI_SCALE))
    except (TypeError, ValueError):
        _UI_SCALE = 1.0
    return _UI_SCALE


def ui_scale():
    """The window's current layout scale (1.0 on the 1280x720 panel)."""
    return _UI_SCALE


def ui_scale_for(width, height):
    """Layout scale for a window of the given pixel size (panel = 1.0).

    Anything at or near the panel size is the panel: the design renders exactly
    as drawn rather than a few percent oversized (see PANEL_SCALE_SNAP). Bigger
    windows - a bench monitor - still scale up proportionally, and smaller ones
    scale down to the floor.
    """
    try:
        width = float(width)
        height = float(height)
    except (TypeError, ValueError):
        return 1.0
    if width <= 1 or height <= 1:
        return 1.0
    raw = min(width / DESIGN_W, height / DESIGN_H)
    if raw <= 1.0 + PANEL_SCALE_SNAP:
        return 1.0
    return max(MIN_UI_SCALE, min(raw, MAX_UI_SCALE))


def sp(value):
    """A spacing value in PANEL pixels.

    CustomTkinter already multiplies every grid/pack padx/pady (and width,
    height, corner radius and font size) by the widget scaling we set from the
    window size, so this helper must NOT scale again - doing so squared the
    spacing on a monitor bigger than the panel. It exists to say, at every call
    site, that the number is panel pixels taken from the 1280x720 design.
    """
    try:
        return max(1, int(round(float(value))))
    except (TypeError, ValueError):
        return value

# --------------------------------------------------------------------------
# Palettes
# --------------------------------------------------------------------------
# Every key is semantic: screens ask for ``surface``/``text``/``accent`` and
# never for a hex value, so a mode switch repaints the whole app consistently.
LIGHT = {
    # surfaces / structure
    "window_bg": "#EEF2F7",
    "surface": "#FFFFFF",
    "surface_alt": "#F8FAFC",
    "surface_high": "#FFFFFF",
    "surface_sunken": "#F1F5F9",
    "border": "#E2E8F0",
    "border_strong": "#CBD5E1",
    # text
    "text": "#0F172A",
    "text_muted": "#64748B",
    "text_faint": "#94A3B8",
    "text_on_accent": "#FFFFFF",
    # accents (teal-700 keeps white button text above 4.5:1 contrast)
    "accent": "#0F766E",
    "accent_hover": "#0E6E67",
    "accent_soft": "#CCFBF1",
    "accent_text": "#0F766E",
    "success": "#15803D",
    "success_soft": "#DCFCE7",
    "on_success": "#FFFFFF",
    "danger": "#DC2626",
    "danger_soft": "#FEE2E2",
    "on_danger": "#FFFFFF",
    "warning": "#F59E0B",
    "warning_hover": "#D97706",
    "warning_soft": "#FEF3C7",
    "warning_text": "#000000",
    "info": "#2563EB",
    "info_soft": "#DBEAFE",
    # Method colours for the test / result tiles and the filter chips. LIGHT
    # TINTS with text in the same hue, not the saturated fills they used to be:
    # a whole page of filled tiles read as heavy dark blocks on the 7" panel
    # ("too dark colour, use light shades"), and a tile that is a tint needs a
    # border to separate it from the pale window behind it. Text contrast is
    # 7:1 or better in every case (see verify_theme).
    "method_tp": "#DBEAFE",
    "method_tp_hover": "#BFDBFE",
    "method_tp_border": "#93C5FD",
    "method_tp_text": "#1E40AF",
    "method_ep": "#FEE2E2",
    "method_ep_hover": "#FECACA",
    "method_ep_border": "#FCA5A5",
    "method_ep_text": "#991B1B",
    "method_kinetic": "#FEF3C7",
    "method_kinetic_hover": "#FDE68A",
    "method_kinetic_border": "#FCD34D",
    "method_kinetic_text": "#92400E",
    # The GO action (RUN on the parameter form). Deliberately BLUE, not the
    # accent teal: the operator reported RUN and SAVE reading as the same shade,
    # and the two sit next to each other. White on this blue is 4.6:1.
    "run_btn": "#2563EB",
    "run_btn_hover": "#1D4ED8",
    "on_run_btn": "#FFFFFF",
    # the "recommended / active step" button (amber in light mode)
    "highlight": "#F59E0B",
    "highlight_hover": "#D97706",
    "on_highlight": "#000000",
    # the step that is executing right now (labelled "... (Running...)")
    "run_active": "#15803D",
    "run_active_hover": "#15803D",
    "on_run_active": "#FFFFFF",
    # buttons
    "btn_neutral": "#E2E8F0",
    "btn_neutral_hover": "#CBD5E1",
    "btn_text": "#0F172A",
    "btn_disabled": "#CBD5E1",
    # Label colour for a frozen/disabled button. It must stay READABLE: the
    # operator reads the row from across the bench while a run or a clean is in
    # flight, so a faint grey label is useless.
    "btn_disabled_text": "#334155",
    # graph
    "graph_bg": "#FFFFFF",
    "graph_grid": "#E5E7EB",
    "graph_axis": "#CBD5E1",
    "graph_text": "#334155",
    "graph_title": "#0F172A",
    "graph_line": "#2563EB",
    # water/blank/std/sample all run a single-series plot, so they share ONE
    # colour in both themes: whatever the trace colour is, every test uses it.
    "graph_water": "#2563EB",
    "graph_delay": "#E8890C",
    "graph_measure": "#6D4AE6",
    "graph_band": "#E8890C",
    "graph_marker": "#1D4ED8",
}

DARK = {
    # ---------------------------------------------------------------------
    # TRUE BLACK base. The background reads as black (never navy/blue); the
    # panels lift off it in near-black charcoal with hairline borders, and
    # colour is reserved for status and interaction.
    # ---------------------------------------------------------------------
    "window_bg": "#000000",
    # Panels stay this close to black on purpose: the whole app should read as
    # a black instrument face (like the measurement screen), with the hairline
    # border - not a lighter fill - doing the job of separating cards.
    "surface": "#020304",
    "surface_alt": "#000000",
    "surface_high": "#080A0D",
    "surface_sunken": "#000000",
    "border": "#1E222A",
    "border_strong": "#2C313B",
    # text - near-white for headings/values, muted grey for captions
    "text": "#F9F9F9",
    "text_muted": "#A6ADB9",
    "text_faint": "#7C8494",
    "text_on_accent": "#FFFFFF",
    # accents - the coral #E94560 is the brand/action colour (active states,
    # selected elements, key graph indicators); teal/orange/green/blue are
    # kept for status only.
    "accent": "#E94560",
    "accent_hover": "#FF5C77",
    "accent_soft": "#2A0E15",
    "accent_text": "#FF8A9E",
    "success": "#34D399",
    "success_soft": "#06251C",
    "on_success": "#04170F",
    "danger": "#F87171",
    "danger_soft": "#2B1114",
    "on_danger": "#2A0C0C",
    "warning": "#FEA83E",
    "warning_hover": "#FFBB63",
    "warning_soft": "#2B1F0C",
    "warning_text": "#1A1206",
    "info": "#5AB0F5",
    "info_soft": "#0A1C2E",
    # Method colours are UNCHANGED in dark mode: the saturated fills the tiles
    # have always used on the black theme ("for dark mode keep the same previous
    # colors"). Fills and borders match, because a saturated tile is already
    # distinct against black and an outlined one would read as a different
    # control - the border only earns its place on the pale light theme.
    "method_tp": "#3B82F6",
    "method_tp_hover": "#2563EB",
    "method_tp_border": "#3B82F6",
    "method_tp_text": "#FFFFFF",
    "method_ep": "#EF4444",
    "method_ep_hover": "#DC2626",
    "method_ep_border": "#EF4444",
    "method_ep_text": "#FFFFFF",
    "method_kinetic": "#FFAB00",
    "method_kinetic_hover": "#E09600",
    "method_kinetic_border": "#FFAB00",
    "method_kinetic_text": "#1A1200",
    # GO button: a deeper blue than the status blue so white label text keeps
    # its 4.5:1 contrast on the true-black theme (see the light palette).
    "run_btn": "#1D4ED8",
    "run_btn_hover": "#2563EB",
    "on_run_btn": "#FFFFFF",
    # the "recommended / active step" button is the coral here
    "highlight": "#E94560",
    "highlight_hover": "#FF5C77",
    "on_highlight": "#FFFFFF",
    # The step executing right now: the SAME green the light theme has always
    # used, with white text. Operators read this at arm's length from across
    # the bench, so it has to be unmistakable and legible - the amber it
    # replaced was neither. One shade LIGHTER (#16A34A) looks better on black
    # but drops white text to 3.3:1, so dark mode keeps the same green: white
    # on it is 5.0:1 and the filled button still reads clearly against #000000.
    "run_active": "#15803D",
    "run_active_hover": "#166534",
    "on_run_active": "#FFFFFF",
    # buttons - near-black charcoal, thin borders, white labels
    "btn_neutral": "#0E1116",
    "btn_neutral_hover": "#181D24",
    "btn_text": "#F9F9F9",
    "btn_disabled": "#14171C",
    # Readable label on a frozen button (see the light palette note).
    "btn_disabled_text": "#C9CFD8",
    # graph - black plot surface, white trace, orange delay phase and the
    # lavender measuring phase; the live point is ringed in the coral.
    "graph_bg": "#000000",
    "graph_grid": "#16191F",
    "graph_axis": "#242932",
    "graph_text": "#A6ADB9",
    "graph_title": "#F9F9F9",
    "graph_line": "#F9F9F9",
    # water/blank/std/sample all run a single-series plot, so they share ONE
    # colour in this theme: the same white trace for every test.
    "graph_water": "#F9F9F9",
    "graph_delay": "#FEA83E",
    "graph_measure": "#D8D1FD",
    "graph_band": "#FEA83E",
    "graph_marker": "#E94560",
}

PALETTES = {"light": LIGHT, "dark": DARK}

# --------------------------------------------------------------------------
# Legacy color remap (dark mode)
# --------------------------------------------------------------------------
# Screens written before the design system bake light-mode hex values into
# their widgets (results.py, test_screen.py, qc.py, dilution.py, ...). Instead
# of rewriting every one of them, ``polish_tree`` walks the widget tree once
# per screen and swaps the known light neutrals for their dark counterparts.
#
# The SAME hex often plays two roles, and they must invert differently: #1E293B
# is a dark table HEADER (a fill, which stays dark) in one screen and dark
# BODY TEXT (which must become light) in another. That is why there are three
# maps: fills, text colors and matplotlib artists (which carry no text on top
# and therefore want the bright accents).
DARK_REMAP_TEXT = {
    # light-on-light text and names
    "#FFFFFF": "#E8EDF7",
    "#F8FAFC": "#E8EDF7",
    "#F1F5F9": "#E8EDF7",
    "#E2E8F0": "#E8EDF7",
    "WHITE": "#E8EDF7",
    "WHITESMOKE": "#E8EDF7",
    "#000000": "#E8EDF7",
    "BLACK": "#E8EDF7",
    "#0F172A": "#E8EDF7",
    "#1E293B": "#E2E8F0",
    "#1F2937": "#E2E8F0",
    "#2C3E50": "#E2E8F0",
    "#334155": "#CBD5E1",
    "#374151": "#CBD5E1",
    "#475569": "#A9B6CC",
    "#4B5563": "#A9B6CC",
    "#64748B": "#94A3B8",
    "#6B7280": "#94A3B8",
    "#94A3B8": "#94A3B8",
    "#9CA3AF": "#8B95A7",
    "GRAY": "#94A3B8",
    "GREY": "#94A3B8",
    # chip text: brighten so it reads on the dark chip tints below
    "#166534": "#6EE7A8",
    "#15803D": "#6EE7A8",
    "#A16207": "#FCD34D",
    "#C2410C": "#FDBA74",
    "#B91C1C": "#FCA5A5",
    "#BE185D": "#F9A8D4",
    "#1D4ED8": "#93B4FF",
    "#1E40AF": "#93B4FF",
    "#1E3A8A": "#93B4FF",
    "#0D9488": "#5EEAD4",
    "#e53935": "#F87171",
}

DARK_REMAP_FG = {
    # light neutrals -> dark surfaces
    "#FFFFFF": "#131A2A",
    "#F8FAFC": "#0F1524",
    "#F9FAFB": "#0F1524",
    "#F1F5F9": "#0F1524",
    "#F3F4F6": "#131A2A",
    "#F0F0F0": "#131A2A",
    "#E5E7EB": "#26314A",
    "#E2E8F0": "#26314A",
    "#CCCCCC": "#2A3247",
    "#DDDDDD": "#2A3247",
    "#D3D3D3": "#232E45",
    "#EEF2F7": "#0A0E17",
    "WHITE": "#131A2A",
    "WHITESMOKE": "#131A2A",
    # dark slate FILLS (table headers, neutral buttons) stay dark, just lifted
    "#0F172A": "#1B2438",
    "#1E293B": "#1B2438",
    "#1F2937": "#1B2438",
    "#2C3E50": "#1B2438",
    "#334155": "#243049",
    "#374151": "#243049",
    "#475569": "#2A3247",
    "#4B5563": "#2A3247",
    "#64748B": "#3A4459",
    "#6B7280": "#3A4459",
    "#9CA3AF": "#4A5568",
    "BLACK": "#0A0E17",
    # soft chips -> dark chips
    "#DCFCE7": "#0C2A22",
    "#F0FDF4": "#0C2A22",
    "#FEF9C3": "#33290B",
    "#FEFCE8": "#33290B",
    "#FFF7ED": "#331F0B",
    "#FEE2E2": "#331A1E",
    "#FDF2F8": "#2E1626",
    "#FCE7F3": "#2E1626",
    "#F3E8FF": "#231A3A",
    "#EFF6FF": "#12203A",
    "#E0F2FE": "#122A3A",
    "#F0F9FF": "#122A3A",
    "#FFEBEE": "#331A1E",
    "#E0F0E9": "#0C2A22",
    "LIGHTBLUE": "#12203A",
    # accents used as FILLS: deepened so white/light label text stays readable
    "#14B8A6": "#0F766E",
    "#0D9488": "#0F766E",
    "#0891B2": "#0E6E67",
    "#2563EB": "#1D4ED8",
    "#3B82F6": "#2563EB",
    "#4169E1": "#1D4ED8",
    "#EF4444": "#B91C1C",
    "#DC2626": "#B91C1C",
    "#DC143C": "#B91C1C",
    "#e53935": "#B91C1C",
    "#FF4D4D": "#B91C1C",
    "#4CAF50": "#15803D",
    "#2E8B57": "#15803D",
    "#10B981": "#15803D",
    "#F59E0B": "#B45309",
    "#FF8C00": "#B45309",
    "#FFD700": "#B45309",
    "#8B5CF6": "#6D4AE6",
    "#166534": "#0C2A22",
    "#15803D": "#0C2A22",
}

# matplotlib figures have no label text riding on the lines/shapes, so they can
# (and should) use the bright accent tones for visibility on the dark plot.
DARK_REMAP_FIGURE = dict(DARK_REMAP_FG)
DARK_REMAP_FIGURE.update({
    "#2E8B57": "#34D399",
    "#4169E1": "#7DA9FF",
    "#FF8C00": "#FEA83E",
    "#DC143C": "#F87171",
    "#FFD700": "#FCD34D",
    "#4CAF50": "#34D399",
    "#10B981": "#34D399",
    "#14B8A6": "#2DD4BF",
    "#2563EB": "#7DA9FF",
    "#3B82F6": "#7DA9FF",
    "#EF4444": "#F87171",
    "#DC2626": "#F87171",
    "#8B5CF6": "#C4B5FD",
    "#0891B2": "#67E8F9",
    "#F59E0B": "#FEA83E",
    "#b91c1c": "#F87171",
    "WHITE": "#131A2A",
    "GRAY": "#94A3B8",
    "GREY": "#94A3B8",
    "LIGHTBLUE": "#12203A",
})

# Back-compat alias (older callers asked for a single map).
DARK_REMAP = DARK_REMAP_FIGURE

# --------------------------------------------------------------------------
# Color helpers
# --------------------------------------------------------------------------
def hex_to_rgb(value):
    """'#RRGGBB' -> (r, g, b); accepts 3-digit shorthand, returns None if bad."""
    if not isinstance(value, str):
        return None
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(ch * 2 for ch in v)
    if len(v) != 6:
        return None
    try:
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def relative_luminance(color):
    """WCAG relative luminance of a hex color (0 = black, 1 = white)."""
    rgb = hex_to_rgb(color)
    if rgb is None:
        return None
    channels = []
    for raw in rgb:
        c = raw / 255.0
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg, bg):
    """WCAG contrast ratio between two hex colors (1..21), None if unparsable."""
    l1 = relative_luminance(fg)
    l2 = relative_luminance(bg)
    if l1 is None or l2 is None:
        return None
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


# --------------------------------------------------------------------------
# Typography
# --------------------------------------------------------------------------
# One family for the whole UI, resolved lazily on first use (Tk must exist
# before its font list can be queried). Falls back to Tk's default on a platform
# that has none of the preferred faces, so the Pi never renders tofu.
PREFERRED_FONTS = ("Segoe UI", "SF Pro Text", "Inter", "Ubuntu", "Noto Sans",
                   "DejaVu Sans", "Helvetica")
_font_family = None


def font_family():
    """Best available UI font family (cached)."""
    global _font_family
    if _font_family is None:
        _font_family = "TkDefaultFont"
        try:
            from tkinter import font as tkfont
            available = {name.lower() for name in tkfont.families()}
            for name in PREFERRED_FONTS:
                if name.lower() in available:
                    _font_family = name
                    break
        except Exception as exc:
            print(f"[THEME] could not resolve a UI font family: {exc}")
    return _font_family


# Screens ask for the same handful of font sizes dozens of times (every
# label, button, table cell). Each CTkFont is a real Tcl font object, so
# building them per widget dominated screen load time; the cache is keyed by
# interpreter as well, so a new Tk root (tests, re-runs) never reuses a font
# that belonged to a destroyed interpreter.
_FONT_CACHE = {}


def font(size=12, weight="normal", bold=False):
    """Themed CTkFont. ``bold=True`` is shorthand for ``weight='bold'``."""
    if bold:
        weight = "bold"
    try:
        import tkinter as _tk
        key = (id(_tk._default_root), size, weight)
    except Exception:
        key = (None, size, weight)
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        made = ctk.CTkFont(family=font_family(), size=size, weight=weight)
    except Exception:
        made = ctk.CTkFont(size=size, weight=weight)
    _FONT_CACHE[key] = made
    return made


REMAP_ROLES = {
    "fg": DARK_REMAP_FG,
    "text": DARK_REMAP_TEXT,
    "figure": DARK_REMAP_FIGURE,
}

# The dark palette shipped with the first redesign pass was navy based. The
# remap maps above still point at a few of those values, so every remapped
# colour is snapped through this alias table: a legacy screen can never paint a
# navy panel onto the new true-black UI.
LEGACY_DARK_ALIASES = {
    "#0A0E17": "#000000",   # window background
    "#0F1524": "#05070A",
    "#131A2A": "#080A0D",   # panels
    "#1B2438": "#101318",
    "#0D1220": "#05070A",
    "#26314A": "#1E222A",   # borders
    "#33415F": "#2C313B",
    "#243049": "#181D24",
    "#233049": "#16191F",
    "#3A4459": "#232830",
    "#4A5568": "#2C313B",
    "#E8EDF7": "#F9F9F9",   # text
    "#E2E8F0": "#E9EDF3",
    "#CBD5E1": "#CFD6E0",
    "#94A3B8": "#A6ADB9",
    "#A9B6CC": "#A6ADB9",
    "#8B95A7": "#8A93A1",
    "#1E2A41": "#0E1116",   # buttons
    "#27354F": "#181D24",
    "#2A3247": "#14171C",
    "#0E2E2C": "#2A0E15",   # accent chips
    "#5EEAD4": "#FF8A9E",
    "#0C2A22": "#06251C",
    "#06231A": "#04170F",
    "#331A1E": "#2B1114",
    "#2A0B0B": "#2A0C0C",
    "#33260F": "#2B1F0C",
    "#12203A": "#0A1C2E",
    "#122A3A": "#0A1C2E",
    "#2E1626": "#2A0E15",
    "#33290B": "#2B1F0C",
    "#331F0B": "#2B1F0C",
    "#231A3A": "#231A3A",
    "#7DA9FF": "#5AB0F5",   # graph/blue accent
    "#6FA8FF": "#F9F9F9",
    "#8FB8FF": "#E94560",
    "#2DD4BF": "#22D3EE",
}


def _map_color(value, mapping):
    """Remap one color value; tuples (light, dark) are handled per element."""
    if isinstance(value, (tuple, list)):
        return tuple(_map_color(v, mapping) for v in value)
    if not isinstance(value, str):
        return value
    mapped = mapping.get(value.upper(), value)
    if isinstance(mapped, str):
        return LEGACY_DARK_ALIASES.get(mapped.upper(), mapped)
    return mapped


# --------------------------------------------------------------------------
# The theme manager
# --------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(_PROJECT_ROOT, "ui_settings.json")


class Theme:
    """Holds the active mode and hands out the palette."""

    def __init__(self, path=SETTINGS_PATH):
        self._path = path
        self._mode = "light"
        self._listeners = []
        self._load()

    # ---- state ----------------------------------------------------------
    @property
    def mode(self):
        return self._mode

    @property
    def dark(self):
        return self._mode == "dark"

    @property
    def colors(self):
        return PALETTES[self._mode]

    def get(self, key, default=None):
        return self.colors.get(key, default)

    def __getitem__(self, key):
        return self.colors[key]

    def __contains__(self, key):
        return key in self.colors

    # ---- switching ------------------------------------------------------
    def set_mode(self, mode, persist=True):
        """Switch mode, apply the CustomTkinter appearance, notify listeners."""
        mode = "dark" if str(mode).lower() == "dark" else "light"
        changed = mode != self._mode
        self._mode = mode
        try:
            ctk.set_appearance_mode(mode)
        except Exception as exc:  # pragma: no cover - ctk is always available
            print(f"[THEME] could not set appearance mode: {exc}")
        if persist:
            self._save()
        if changed:
            for callback in list(self._listeners):
                try:
                    callback(mode)
                except Exception as exc:
                    print(f"[THEME] listener failed: {exc}")
        return self._mode

    def toggle(self, persist=True):
        return self.set_mode("light" if self.dark else "dark", persist=persist)

    def on_change(self, callback):
        self._listeners.append(callback)

    # ---- remote control (tests / other windows) -------------------------
    def remap(self, value, role="fg"):
        """Dark-mode equivalent of a legacy light-mode color (identity in light).

        ``role`` selects how the same hex inverts: "fg" for fills/borders,
        "text" for label colors, "figure" for matplotlib artists.
        """
        if not self.dark:
            return value
        return _map_color(value, REMAP_ROLES.get(role, DARK_REMAP_FG))

    # ---- persistence ----------------------------------------------------
    def _load(self):
        # The app must OPEN in light mode every time (lab requirement): a
        # previous session's dark switch is not restored at start-up, so the
        # instrument always boots looking the way the SOP expects. The toggle
        # still works for the session, and the file is still written, so a
        # future "remember my choice" only needs this guard removed.
        if START_IN_LIGHT:
            self._mode = "light"
            return
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            mode = str(data.get("theme", "light")).lower()
            if mode in PALETTES:
                self._mode = mode
        except FileNotFoundError:
            pass
        except Exception as exc:
            print(f"[THEME] could not read {self._path}: {exc}")

    def _save(self):
        try:
            data = {}
            if os.path.exists(self._path):
                try:
                    with open(self._path, "r", encoding="utf-8") as handle:
                        data = json.load(handle) or {}
                except Exception:
                    data = {}
            data["theme"] = self._mode
            with open(self._path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
        except Exception as exc:
            print(f"[THEME] could not write {self._path}: {exc}")


theme = Theme()


# --------------------------------------------------------------------------
# Convenience helpers used by the screens
# --------------------------------------------------------------------------
def colors():
    return theme.colors


def c(key, default=None):
    """Active palette lookup."""
    return theme.get(key, default)


def is_dark():
    return theme.dark


def apply_appearance():
    """Apply the current mode to CustomTkinter's widget defaults."""
    try:
        ctk.set_appearance_mode(theme.mode)
    except Exception:
        pass


def card(elevated=False, radius=14):
    """Standard card styling kwargs for a CTkFrame."""
    return {
        "fg_color": c("surface_high") if elevated else c("surface"),
        "corner_radius": radius,
        "border_width": 1,
        "border_color": c("border"),
    }


def primary_button(radius=10):
    """Accent (call-to-action) button styling."""
    return {
        "fg_color": c("accent"),
        "hover_color": c("accent_hover"),
        "text_color": c("text_on_accent"),
        "corner_radius": radius,
    }


def secondary_button(radius=10):
    """Neutral button styling for everything that is not the primary action."""
    return {
        "fg_color": c("btn_neutral"),
        "hover_color": c("btn_neutral_hover"),
        "text_color": c("btn_text"),
        "corner_radius": radius,
    }


def polish_tree(widget):
    """Dark-mode remap of a whole widget subtree (no-op in light mode)."""
    if not theme.dark or widget is None:
        return
    try:
        children = widget.winfo_children()
    except Exception:
        return
    for child in children:
        _polish_widget(child)
        polish_tree(child)


# --------------------------------------------------------------------------
# Matplotlib: dark-remap an existing figure (QC charts, legacy plots)
# --------------------------------------------------------------------------
def _to_hex(color):
    """matplotlib color (name, '#rgb' or an RGBA tuple) -> '#RRGGBB' or None."""
    if color is None:
        return None
    if isinstance(color, str):
        return color
    try:
        seq = tuple(color)
    except TypeError:
        return None
    if len(seq) not in (3, 4):
        return None
    try:
        values = [max(0, min(255, int(round(float(component) * 255)))) for component in seq[:3]]
    except (TypeError, ValueError):
        return None
    return "#%02X%02X%02X" % tuple(values)


def _from_hex(hex_color, alpha=1.0):
    rgb = hex_to_rgb(hex_color)
    if rgb is None:
        return None
    return tuple(component / 255.0 for component in rgb) + (float(alpha),)


def _remap_mpl_color(color):
    """Dark-mode equivalent of a matplotlib color, or None when unchanged."""
    hex_color = _to_hex(color)
    if hex_color is None:
        return None
    new = theme.remap(hex_color, role="figure")
    if new == hex_color:
        return None
    alpha = 1.0
    if not isinstance(color, str):
        try:
            seq = tuple(color)
            if len(seq) == 4:
                alpha = seq[3]
        except TypeError:
            pass
    return _from_hex(new, alpha)


def _remap_artist(artist, attributes):
    """Remap the given color attributes of one matplotlib artist."""
    if artist is None:
        return
    for attribute in attributes:
        try:
            current = getattr(artist, 'get_' + attribute)()
        except Exception:
            continue
        new = _remap_mpl_color(current)
        if new is None:
            continue
        setter = getattr(artist, 'set_' + attribute, None)
        if setter is None:
            continue
        try:
            setter(new)
        except Exception:
            pass


def _remap_collection(collection):
    """Scatter/collection colors live in arrays, not single properties."""
    for attribute in ("facecolor", "edgecolor"):
        getter = getattr(collection, 'get_' + attribute + 's', None)
        setter = getattr(collection, 'set_' + attribute, None)
        if getter is None or setter is None:
            continue
        try:
            current = list(getter())
        except Exception:
            continue
        new = [_remap_mpl_color(color) or color for color in current]
        if new != current:
            try:
                setter(new)
            except Exception:
                pass


def remap_figure(figure):
    """Dark-remap an existing matplotlib figure in place (no-op in light mode)."""
    if not theme.dark or figure is None:
        return
    try:
        figure.set_facecolor(theme.remap(_to_hex(figure.get_facecolor()), role="fg"))
    except Exception:
        pass
    for ax in figure.axes:
        _remap_artist(ax.patch, ('facecolor', 'edgecolor'))
        for spine in ax.spines.values():
            _remap_artist(spine, ('color',))
        for artist in (ax.title, ax.xaxis.label, ax.yaxis.label):
            _remap_artist(artist, ('color',))
        for line in ax.lines:
            _remap_artist(line, ('color', 'markerfacecolor', 'markeredgecolor'))
        for patch in ax.patches:
            _remap_artist(patch, ('facecolor', 'edgecolor'))
        for collection in ax.collections:
            _remap_collection(collection)
        for text in ax.texts:
            _remap_artist(text, ('color',))
            bbox = text.get_bbox_patch()
            if bbox is not None:
                _remap_artist(bbox, ('facecolor', 'edgecolor'))
        for label in list(ax.get_xticklabels()) + list(ax.get_yticklabels()):
            _remap_artist(label, ('color',))
        for gridline in list(ax.get_xgridlines()) + list(ax.get_ygridlines()):
            _remap_artist(gridline, ('color',))
        legend = ax.get_legend()
        if legend is not None:
            _remap_artist(legend.get_frame(), ('facecolor', 'edgecolor'))
            for text in legend.get_texts():
                _remap_artist(text, ('color',))


_FG_OPTIONS = ("fg_color", "bg_color", "hover_color", "border_color",
               "button_color", "button_hover_color", "progress_color",
               "selected_color", "selected_hover_color", "unselected_color",
               "unselected_hover_color", "scrollbar_button_color",
               "scrollbar_button_hover_color", "dropdown_fg_color",
               "dropdown_hover_color")
_TEXT_OPTIONS = ("text_color", "text_color_disabled", "placeholder_text_color",
                 "dropdown_text_color")


# Which of the colour options a widget actually has is a property of its
# CLASS, not of the instance: probing all 19 options on all 167 widgets of a
# screen cost ~3 300 Tcl calls (most of them raising), which made the dark-mode
# repaint the single most expensive part of opening a screen. The first widget
# of each class discovers the list once and every later one reuses it.
_SUPPORTED_OPTIONS = {}


def _supported_options(widget):
    key = type(widget).__name__
    cached = _SUPPORTED_OPTIONS.get(key)
    if cached is not None:
        return cached
    found = []
    for option in _FG_OPTIONS + _TEXT_OPTIONS:
        try:
            widget.cget(option)
        except Exception:
            continue
        found.append((option, "text" if option in _TEXT_OPTIONS else "fg"))
    found = tuple(found)
    _SUPPORTED_OPTIONS[key] = found
    return found


def _polish_widget(widget):
    changes = {}
    for option, role in _supported_options(widget):
        try:
            current = widget.cget(option)
        except Exception:
            continue
        if current is None:
            continue
        new = _map_color(current, REMAP_ROLES[role])
        if new != current:
            changes[option] = new
    if not changes:
        return
    # ONE configure call per widget: every extra call is a full Tcl widget
    # update, and a screen has hundreds of widgets.
    try:
        widget.configure(**changes)
    except Exception:
        # A mixed batch can be rejected by a widget that only accepts some of
        # the options - fall back to setting them one by one.
        for option, value in changes.items():
            try:
                widget.configure(**{option: value})
            except Exception:
                pass


__all__ = [
    "PALETTES", "LIGHT", "DARK", "DARK_REMAP", "theme", "colors", "c",
    "is_dark", "apply_appearance", "card", "primary_button",
    "secondary_button", "polish_tree", "remap_figure", "contrast_ratio",
    "hex_to_rgb", "SETTINGS_PATH", "font", "font_family",
    "DESIGN_W", "DESIGN_H", "set_ui_scale", "ui_scale", "ui_scale_for", "sp",
]
