#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Deprecated shim -- use ``holo process`` (or ``python -m holo``).

Kept so existing notes, scripts and muscle memory keep working. The folder
processing itself now lives in ``holo.cli`` (argument parsing) and
``holo.discovery`` (finding and staging frames), where the GUI can reach it
too.
"""

import sys

from holo.cli import main

if __name__ == "__main__":
    sys.stderr.write("note: process.py is deprecated — use 'holo process'\n")
    sys.exit(main(["process"] + sys.argv[1:]))
