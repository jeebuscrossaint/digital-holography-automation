# -*- coding: utf-8 -*-
"""Photonic-lantern digital holography — the library.

Everything that knows physics lives here. The GUI (``gui/``) and the CLI
(``holo.cli``) are both thin front ends over this package and share every line
of analysis code; neither one is allowed to hold reconstruction logic of its
own. If you are changing behaviour, change it here.

    from holo import HolographyDataProcessor, MultiPortReconstructor
    from holo import pipeline, discovery

Two reconstruction engines, described in detail in ``CLAUDE.md``:

* ``data_processing.HolographyDataProcessor`` -- single-frame. Estimates the
  carrier from one hologram; the only option for a single-leg dataset.
* ``multiport_reconstruction.MultiPortReconstructor`` -- the paper's cross-port
  method. Needs >= 2 legs and is far more accurate.

``pipeline.process_records`` runs both over a sweep and keeps, per frame,
whichever scored higher -- so the result can never be worse than single-frame.
That combination rule exists once, in ``pipeline``, and both front ends call it.

Submodules are imported lazily: ``import holo`` must stay cheap enough for the
CLI's ``--help`` and must not drag in matplotlib or any instrument driver.
"""

__all__ = [
    "HolographyDataProcessor",
    "MultiPortReconstructor",
    "pipeline",
    "discovery",
    "fringe_detection",
    "config",
    "__version__",
]

__version__ = "0.2.0"


def __getattr__(name):
    """Lazy submodule/symbol access -- keeps `import holo` light.

    data_processing pulls in matplotlib, which costs ~0.5 s and is pointless
    for `holo --help` or `holo doctor`.
    """
    if name == "HolographyDataProcessor":
        from .data_processing import HolographyDataProcessor
        return HolographyDataProcessor
    if name == "MultiPortReconstructor":
        from .multiport_reconstruction import MultiPortReconstructor
        return MultiPortReconstructor
    if name in ("pipeline", "discovery", "fringe_detection", "config",
                "data_processing", "multiport_reconstruction"):
        import importlib
        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(__all__)
