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


def _cap_blas_threads(default=4):
    """Cap the BLAS thread pool before numpy is imported.

    This reconstruction is thousands of SMALL contractions -- a (23, 16384)
    basis against one or a few dozen candidate fields. OpenBLAS defaults to one
    thread per core, and at that size the thread hand-off can cost more than
    the arithmetic. On one modeDecomp call, on a 16-core box:

        threads    1     2     4     8    16 (default)
        us/call  220   220   222   409   2400

    That 11x is NOT the end-to-end gain -- the batched GEMMs in the offset and
    phase searches genuinely do use the extra cores. Interleaved A/B over a
    380-frame sweep (19 legs x 20 wavelengths), two replicates each:

         4 threads   261, 271 ms/frame   (mean 266)
        16 threads   326, 300 ms/frame   (mean 313)   -> 1.18x

    Four wins both replicates. Beware small benchmarks here: a 57-frame sweep
    reports 414 ms/frame at 16 threads vs 307 for 380 frames, because building
    the mode basis and spinning up the pool are fixed costs that have not
    amortised yet -- measuring that and calling it throughput is how this
    function first got attributed a 1.38x it does not deliver. Run-to-run
    variance on a full sweep is ~8%, so compare interleaved, never two runs
    minutes apart.

    Only applies when nothing has been set explicitly, so
    ``OPENBLAS_NUM_THREADS=16 holo process ...`` still wins. Must run before
    numpy is first imported -- hence its position here, and why this module
    imports nothing heavy at top level.
    """
    import os
    knobs = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
             "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")
    if any(os.environ.get(k) for k in knobs):
        return                                  # caller has an opinion; respect it
    n = str(min(default, os.cpu_count() or 1))
    for k in knobs:
        os.environ.setdefault(k, n)


_cap_blas_threads()


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
