# -*- coding: utf-8 -*-
"""``python -m holo`` -- same entry point as the ``holo`` console script."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
