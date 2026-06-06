# -*- coding: utf-8 -*-
"""PySide6 (Qt6) GUI for the photonic-lantern digital holography control app.

The app is one ``HolographyApp`` window (see ``gui.app``) — a ``QMainWindow``
composed from a set of mixins, one per concern, so the code stays split into
focused, navigable files. Each mixin operates on the shared ``self`` of the app
instance; none is meant to be instantiated on its own. Worker threads talk to
the GUI only by emitting a Qt signal (``self._post``), which Qt delivers on the
GUI thread — so blocking hardware I/O never freezes the window.
"""
