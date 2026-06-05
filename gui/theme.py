# -*- coding: utf-8 -*-
"""Windows 11 Fluent colors + the ThemeMixin that applies the sv-ttk theme
and picks fonts. The theme itself (backgrounds, buttons, tabs) comes from
sv-ttk; these constants drive the status indicators and the log panel."""

from tkinter import ttk, font as tkfont

ACCENT_GREEN  = "#16C60C"   # Windows accent: success
ACCENT_AMBER  = "#FFB900"   # Windows accent: caution
ACCENT_RED    = "#E81123"   # Windows accent: danger
ACCENT_BLUE   = "#0078D4"   # Windows accent: info
MUTED         = "#888888"

HW_STATUS_COLOR = {
    "connected":    ACCENT_GREEN,
    "disconnected": MUTED,
    "connecting":   ACCENT_AMBER,
    "error":        ACCENT_RED,
}

HW_STATUS_TEXT = {
    "connected":    "Online",
    "disconnected": "Offline",
    "connecting":   "Connecting…",
    "error":        "Error",
}

LOG_TAG_COLOR = {
    "INFO":  None,             # default theme foreground
    "OK":    ACCENT_GREEN,
    "WARN":  ACCENT_AMBER,
    "ERROR": ACCENT_RED,
    "DEBUG": MUTED,
}


class ThemeMixin:
    """Applies the sv-ttk theme and sets up the app's font palette."""

    def _setup_theme(self):
        # Sun Valley (Windows 11 Fluent) — affects ttk widgets globally
        try:
            import sv_ttk
            sv_ttk.set_theme("dark")
        except Exception:
            pass  # falls back to default theme; app still works

        families = set(tkfont.families(self.root))
        body    = "Segoe UI Variable Text"    if "Segoe UI Variable Text"    in families else "Segoe UI"
        display = "Segoe UI Variable Display" if "Segoe UI Variable Display" in families else "Segoe UI"
        small   = "Segoe UI Variable Small"   if "Segoe UI Variable Small"   in families else "Segoe UI"
        mono    = "Cascadia Mono"             if "Cascadia Mono"             in families else "Consolas"

        self._font_body    = (body,    10)
        self._font_body_bold = (body,  10, "bold")
        self._font_section = (body,    11, "bold")
        self._font_title   = (display, 18)
        self._font_subtitle = (display, 11)
        self._font_metric  = (display, 13)
        self._font_small   = (small,    9)
        self._font_mono    = (mono,     9)

        self.root.option_add("*Font", f"{{{body}}} 10")

        # The Treeview heading font isn't picked up from option_add — set explicitly
        s = ttk.Style()
        s.configure("Treeview",          rowheight=26, font=self._font_body)
        s.configure("Treeview.Heading",  font=self._font_body_bold)
        # Reserve a card-ish frame style for grouped sections
        s.configure("Card.TFrame")  # sv-ttk already styles ttk.Frame nicely
