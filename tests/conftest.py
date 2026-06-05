# -*- coding: utf-8 -*-
"""Pytest setup — put the repo root and lib/ on sys.path so the tests can
import the pipeline modules (data_processing, fringe_detection) and Caleb's
lib helpers the same way the app does at runtime."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / "lib"), str(ROOT / "hardware")):
    if p not in sys.path:
        sys.path.insert(0, p)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
