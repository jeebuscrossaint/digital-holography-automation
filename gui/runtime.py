# -*- coding: utf-8 -*-
"""GUI runtime: environment bootstrap + session logfile.

The bootstrap itself (frozen-build paths, the Xeneth DLL search path, seeding
the editable config) now lives in ``holo.runtime`` so the CLI can do hardware
work without importing Qt. This module runs it on import and re-exports the
paths under their historical names, then adds the one thing that is genuinely
GUI-only: redirecting stdout into a session logfile.

Importing this MUST happen before any hardware driver is imported. main.py
does that.
"""

import sys

from holo import runtime as _rt

_rt.bootstrap()

# Re-exported for the GUI modules that already import these names.
SCRIPT_DIR = _rt.SCRIPT_DIR
DATA_DIR = _rt.DATA_DIR
CONFIG_FILE = str(_rt.CONFIG_FILE)

# ── Session logfile ────────────────────────────────────────────────────────────
# Everything goes here: the GUI Activity messages (via HolographyApp._log) AND
# the driver/optimizer print() spam (via stdout redirect), so there's one
# readable record of a session even if it crashes. Lives next to main.py / exe.

LOG_FILE = None
LOG_PATH = str(DATA_DIR / "session.log")


def setup_logfile():
    """Open the session logfile and route stdout into it. Windows Terminal
    chokes on the volume + unicode (µ, °, ✓), and a file means the full log
    survives a crash. Real errors still hit stderr/terminal. The GUI Activity
    panel is unaffected (it has its own queue) — _log mirrors into this file."""
    global LOG_FILE
    import datetime
    try:
        LOG_FILE = open(LOG_PATH, "a", buffering=1, encoding="utf-8")
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        LOG_FILE.write(f"\n===== session {stamp} =====\n")
        sys.stdout = LOG_FILE          # capture driver/optimizer print() too
        sys.__stderr__.write(f"[logging everything to {LOG_PATH}]\n")
    except Exception as e:
        try:
            sys.__stderr__.write(f"(logfile setup failed: {e})\n")
        except Exception:
            pass


def log_line(ts: str, level: str, text: str):
    """Mirror one Activity line into the session logfile (with level). Reads
    the module global at call time so it sees the handle setup_logfile() opens."""
    if LOG_FILE is not None:
        try:
            LOG_FILE.write(f"[{ts}] [{level:5}] {text}\n")
        except Exception:
            pass
