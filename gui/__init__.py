# -*- coding: utf-8 -*-
"""Tkinter GUI for the photonic-lantern digital holography control app.

The app is one ``HolographyApp`` window (see ``gui.app``) composed from a set
of mixins — one per concern — so the ~1900-line monolith is split into focused,
navigable files. Each mixin operates on the shared ``self`` of the app
instance; none is meant to be instantiated on its own.
"""
