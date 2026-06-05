# -*- coding: utf-8 -*-
"""UCF CREOL — Photonic Lantern Digital Holography Control.

Run with: python main.py

The app itself lives in the ``gui`` package — this is just the launcher.
Importing ``gui.runtime`` first runs the environment bootstrap (frozen-build
paths, the Xeneth DLL search path, and sys.path for hardware/ and lib/) that
must happen before any hardware driver is imported.
"""

import gui.runtime  # noqa: F401  — import for its bootstrap side effects
from gui.app import main

if __name__ == "__main__":
    main()
