# -*- coding: utf-8 -*-
"""Pytest setup.

Only the repo root goes on sys.path, so ``import holo`` resolves the same way
it will once the package is installed. lib/ and hardware/ used to be appended
too, because they were bare directories rather than packages; they are
``holo.lib`` and ``holo.hardware`` now and need no help.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).resolve().parent / "fixtures"
