# -*- coding: utf-8 -*-
"""Environment bootstrap + session logfile.

Importing this module sets up the runtime environment — frozen-build paths,
the Xeneth DLL search path, and sys.path for the hardware/ and lib/ packages.
It MUST be imported before any hardware driver is imported (the drivers are
imported lazily inside GUI methods, so importing this module first — as main.py
does — is sufficient).
"""

import os
import sys
from pathlib import Path

# ── Frozen-build paths ───────────────────────────────────────────────────────

_FROZEN = getattr(sys, "frozen", False)
if _FROZEN:
    # PyInstaller one-file build: bundled code/resources live under _MEIPASS,
    # but editable data (config, logs, holograms) must live NEXT TO the .exe.
    SCRIPT_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    DATA_DIR = Path(sys.executable).parent
    os.chdir(DATA_DIR)               # so "./holography_data" etc. land by the exe
else:
    # gui/runtime.py -> repo root is one level up from the gui package.
    SCRIPT_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = SCRIPT_DIR

# Add Xeneth DLL to Windows DLL search path
_XENETH_RUNTIME = r"C:\Program Files\Common Files\XenICs\Runtime"
if os.path.exists(_XENETH_RUNTIME):
    try:
        os.add_dll_directory(_XENETH_RUNTIME)
    except AttributeError:
        pass  # Python < 3.8
    os.environ["PATH"] = _XENETH_RUNTIME + os.pathsep + os.environ.get("PATH", "")

# Hardware driver paths (hardware/) and processing libs (lib/)
for _p in (str(SCRIPT_DIR / "hardware"), str(SCRIPT_DIR / "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

CONFIG_FILE = str(DATA_DIR / "experiment_config.yaml")
# On a frozen build's first run, seed the editable config from the bundled default.
if _FROZEN and not os.path.exists(CONFIG_FILE):
    import shutil
    _default_cfg = SCRIPT_DIR / "experiment_config.yaml"
    if _default_cfg.exists():
        try:
            shutil.copy(str(_default_cfg), CONFIG_FILE)
        except Exception:
            pass

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
