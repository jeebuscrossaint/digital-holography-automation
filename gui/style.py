# -*- coding: utf-8 -*-
"""Windows 11 Fluent-ish dark theme for the Qt app.

Replaces the old sv-ttk (tkinter) theming. Applies a Fusion-based dark
palette + a stylesheet to the QApplication, and exposes the status-indicator
colors / text the hardware bar and Activity log use (ported verbatim from the
old theme.py so behaviour matches)."""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ACCENT_GREEN = "#16C60C"   # Windows accent: success
ACCENT_AMBER = "#FFB900"   # Windows accent: caution
ACCENT_RED   = "#E81123"   # Windows accent: danger
ACCENT_BLUE  = "#0078D4"   # Windows accent: info
MUTED        = "#888888"

BG       = "#1c1c1c"
BG_CARD  = "#242424"
BG_INPUT = "#2d2d2d"
FG       = "#e6e6e6"
BORDER   = "#3a3a3a"

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

# Activity log colours by level (None = default foreground)
LOG_TAG_COLOR = {
    "INFO":  FG,
    "OK":    ACCENT_GREEN,
    "WARN":  ACCENT_AMBER,
    "ERROR": ACCENT_RED,
    "DEBUG": MUTED,
}

_STYLESHEET = f"""
QWidget {{ background: {BG}; color: {FG}; font-size: 10pt; }}
QLabel#Title {{ font-size: 18pt; }}
QLabel#Section {{ font-size: 11pt; font-weight: bold; }}
QLabel#Metric {{ font-size: 13pt; }}
QLabel#BigReadout {{ font-size: 26pt; }}
QLabel#Muted {{ color: {MUTED}; }}
QLabel#Small {{ color: {MUTED}; font-size: 9pt; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 6px; top: -1px; }}
QTabBar::tab {{
    background: {BG_CARD}; padding: 8px 18px; margin-right: 2px;
    border-top-left-radius: 6px; border-top-right-radius: 6px; color: {MUTED};
}}
QTabBar::tab:selected {{ background: {BG_INPUT}; color: {FG}; }}

QGroupBox {{
    border: 1px solid {BORDER}; border-radius: 8px; margin-top: 10px;
    padding: 12px; font-weight: bold;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {MUTED}; }}

QPushButton {{
    background: {BG_INPUT}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 6px 14px;
}}
QPushButton:hover {{ background: #383838; }}
QPushButton:disabled {{ color: #555; border-color: #2a2a2a; }}
QPushButton#Accent {{ background: {ACCENT_BLUE}; border: none; color: white; }}
QPushButton#Accent:hover {{ background: #1a86d9; }}
QPushButton#Accent:disabled {{ background: #2a3f52; color: #6f8597; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {BG_INPUT}; border: 1px solid {BORDER}; border-radius: 6px; padding: 4px 6px;
}}
QProgressBar {{
    background: {BG_INPUT}; border: 1px solid {BORDER}; border-radius: 6px;
    text-align: center; height: 18px;
}}
QProgressBar::chunk {{ background: {ACCENT_BLUE}; border-radius: 5px; }}

QTextEdit#Log {{
    background: #1a1a1a; border: none; border-radius: 6px;
    font-family: "Cascadia Mono", Consolas, monospace; font-size: 9pt;
}}
QTreeWidget {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 6px; }}
QHeaderView::section {{ background: {BG_INPUT}; padding: 5px; border: none; font-weight: bold; }}
QScrollArea {{ border: none; }}
"""


def apply_theme(app: QApplication):
    """Apply the Fusion dark palette + stylesheet to the whole app."""
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window,          QColor(BG))
    pal.setColor(QPalette.WindowText,      QColor(FG))
    pal.setColor(QPalette.Base,            QColor(BG_INPUT))
    pal.setColor(QPalette.AlternateBase,   QColor(BG_CARD))
    pal.setColor(QPalette.Text,            QColor(FG))
    pal.setColor(QPalette.Button,          QColor(BG_INPUT))
    pal.setColor(QPalette.ButtonText,      QColor(FG))
    pal.setColor(QPalette.Highlight,       QColor(ACCENT_BLUE))
    pal.setColor(QPalette.HighlightedText, QColor("white"))
    pal.setColor(QPalette.ToolTipBase,     QColor(BG_CARD))
    pal.setColor(QPalette.ToolTipText,     QColor(FG))
    app.setPalette(pal)
    app.setStyleSheet(_STYLESHEET)
