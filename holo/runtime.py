# -*- coding: utf-8 -*-
"""Environment bootstrap shared by every front end.

Both the GUI and the CLI need the same three things settled before any driver
is imported: where editable data lives (next to the .exe in a frozen build, the
repo root otherwise), the Xeneth DLL search path on Windows, and a config file
that exists. This used to live in ``gui/runtime.py``, which meant the CLI could
not touch hardware without importing Qt.

``bootstrap()`` is idempotent -- call it from any entry point.
"""

import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    # PyInstaller one-file build: bundled code/resources live under _MEIPASS,
    # but editable data (config, logs, holograms) must live NEXT TO the .exe.
    SCRIPT_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    DATA_DIR = Path(sys.executable).parent
else:
    # holo/runtime.py -> repo root is one level up from the holo package.
    SCRIPT_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = SCRIPT_DIR

CONFIG_FILE = DATA_DIR / "experiment_config.yaml"

_XENETH_RUNTIME = r"C:\Program Files\Common Files\XenICs\Runtime"
_done = False


def bootstrap():
    """Prepare the process for hardware access. Safe to call more than once."""
    global _done
    if _done:
        return
    _done = True

    if FROZEN:
        os.chdir(DATA_DIR)           # so "./holography_data" etc. land by the exe

    # Xeneth's DLLs are not on PATH by default; XenicsCam fails to import
    # without this. No-op off Windows.
    if os.path.isdir(_XENETH_RUNTIME):
        try:
            os.add_dll_directory(_XENETH_RUNTIME)
        except (AttributeError, OSError):
            pass
        os.environ["PATH"] = _XENETH_RUNTIME + os.pathsep + os.environ.get("PATH", "")

    # On a frozen build's first run, seed the editable config from the bundle.
    if FROZEN and not CONFIG_FILE.exists():
        import shutil
        default_cfg = SCRIPT_DIR / "experiment_config.yaml"
        if default_cfg.exists():
            try:
                shutil.copy(str(default_cfg), str(CONFIG_FILE))
            except OSError:
                pass
