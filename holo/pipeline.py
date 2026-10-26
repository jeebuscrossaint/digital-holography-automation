# -*- coding: utf-8 -*-
"""The hologram-processing pipeline — one implementation, two front ends.

Both the GUI's *Process* button (``gui.experiment``) and the headless CLI
(``process.py``) run this module. It is deliberately the only place that knows
how the two reconstruction engines are combined:

  * **single-frame** (``data_processing.HolographyDataProcessor``) — works on
    one hologram at a time; the only option for a single-leg dataset.
  * **multiport** (``multiport_reconstruction.MultiPortReconstructor``) — the
    paper's cross-port method; needs >= 2 legs, because its accuracy comes from
    averaging the carrier centroid over all ports at each wavelength.

Multiport runs once over the whole sweep, then each frame keeps whichever
engine scored higher, so the result can never be worse than single-frame.

A caller supplies *records* — one dict per frame::

    {"path": Path, "label": str, "leg": int | None, "wl": float}

and a ``log(text, level)`` callback. That is the whole contract.
"""

from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

from .fringe_detection import check_saturation

# Filename layout the multiport engine expects; process.py stages arbitrary
# inputs into this form, and the collector writes it natively.
MULTIPORT_FMT = "leg{leg:02d}-wavelength{wl:04d}.npy"

# Reference frames are indexed by wavelength; a reference this far (nm) from
# the frame's wavelength is not close enough to subtract.
BACKGROUND_MAX_DETUNING_NM = 2.0


def _noop_log(text, level="INFO"):
    pass


# ── background references ────────────────────────────────────────────────────

def nearest_background(ref_index, wl, load, log=_noop_log):
    """Pick the reference frame closest in wavelength, or None if none is close.

    The background is the reference beam alone; it removes the low-frequency
    envelope that otherwise drags fidelity down. It is wavelength-dependent, so
    a reference taken at a different lambda is worse than no reference at all —
    hence the detuning limit. References are leg-independent (the reference beam
    never passes through the lantern), so wavelength is the only key.
    """
    if not ref_index:
        return None
    nearest = min(ref_index, key=lambda w: abs(w - float(wl)))
    if abs(nearest - float(wl)) <= BACKGROUND_MAX_DETUNING_NM:
        return load(ref_index[nearest])
    log(f"  (nearest reference {nearest} nm too far from {wl} nm — skipping bg)",
        "DEBUG")
    return None


# ── multiport pass ───────────────────────────────────────────────────────────

def run_multiport(data_dir, legs, wavelengths, config, log=_noop_log):
    """Run the cross-port reconstruction over the whole sweep.

    Returns ``{(leg, wl): frame_result}``, or ``{}`` if it could not run — the
    caller then just uses single-frame results.
    """
    from .multiport_reconstruction import MultiPortReconstructor

    # Fiber parameters for the multiport basis. NOTE these are deliberately a
    # separate config block from `processing.core_radius` (which sizes the
    # single-frame basis) because the two currently disagree about the same
    # physical lantern — see CLAUDE.md, "Two open physics questions".
    mp_cfg = (config.get("processing") or {}).get("multiport", {})
    log(f"Multi-leg dataset ({len(legs)} legs) — running multiport "
        f"reconstruction (paper cross-port method)…", "INFO")
    try:
        mp = MultiPortReconstructor(
            data_dir, legs, wavelengths,
            filename_fmt=MULTIPORT_FMT,
            crop_size=200, nfft=64, mode_size=180,
            core_radius=float(mp_cfg.get("core_radius", 12e-6)),
            NA=float(mp_cfg.get("numerical_aperture", 0.11)),
            n_eff=float(mp_cfg.get("effective_index", 1.453)),
            # FOV (um) the 64-px field spans. 40 was the floor and railed: the
            # Aug 4 7-port sweep fits best at 28-43 um.
            diameter_range=(20, 90),
            pol_half=None,                       # single-polarisation rig
            ref_wavelength=wavelengths[0])
        out = mp.reconstruct_all()
        log(f"Multiport mean fidelity {float(np.mean(out['fidelity'])):.3f} — "
            f"keeping the better of multiport/single-frame per frame", "INFO")
        return out.get("frames", {})
    except Exception as e:
        import traceback
        log(f"Multiport unavailable ({e}) — single-frame only", "WARN")
        log(traceback.format_exc(), "DEBUG")
        return {}


# ── one frame ────────────────────────────────────────────────────────────────

_RESULT_KEYS = ("fidelity", "mode_powers", "mode_decomposition",
                "recovered_field_corrected")


def _single_frame(proc, rec, *, load, background, ref_index, bg_modifier,
                  save, show, sat_level=65535, sat_frac_max=0.001,
                  log=_noop_log):
    """Load, background-subtract and reconstruct one record.

    Depends only on the record, so the serial loop and the worker pool both
    call it and produce the same numbers. A clipped frame is still
    reconstructed (raw data is never dropped) but comes back flagged: its
    fidelity is not a measurement."""
    hologram = proc.load_hologram(rec["path"])
    sat = check_saturation(hologram, sat_level=sat_level,
                           sat_fraction_max=sat_frac_max)
    bg = background
    if bg is None:
        bg = nearest_background(ref_index, rec["wl"], load, log)
    res = proc.process_single_hologram(
        hologram, wavelength_nm=rec["wl"], show_plots=show, save_plots=save,
        plot_prefix=rec["label"], background=bg, bg_modifier=bg_modifier)
    out = {k: res[k] for k in _RESULT_KEYS}
    out["saturated"] = bool(sat["saturated"])
    out["saturated_fraction"] = float(sat["fraction"])
    return out


# Per-worker state, set once by _worker_init so the processor and any
# background frame are pickled once per worker, not once per frame.
_WORKER = {}


def _worker_init(kwargs):
    _WORKER.update(kwargs)


def _worker_frame(rec):
    try:
        return _single_frame(rec=rec, **_WORKER), None
    except Exception:
        import traceback
        return None, traceback.format_exc()


def _frame_results(proc, records, workers, frame_kw, log, should_stop):
    """Yield (index, result, traceback) for every record.

    workers <= 1 runs in this process, in record order. Otherwise frames run
    in a process pool, submitted grouped by wavelength so one worker reuses
    one LP-mode basis for every leg at that wavelength (building the basis is
    the costliest step that is not per-frame); results arrive in that order.
    """
    if workers <= 1:
        for i, rec in enumerate(records):
            if should_stop():
                return
            try:
                yield i, _single_frame(proc, rec, log=log, **frame_kw), None
            except Exception:
                import traceback
                yield i, None, traceback.format_exc()
        return

    import copy
    import multiprocessing
    import os
    from concurrent.futures import ProcessPoolExecutor

    worker_proc = copy.copy(proc)
    worker_proc._mode_cache = {}             # don't ship the parent's cache
    order = sorted(range(len(records)),
                   key=lambda i: (records[i]["wl"], records[i]["leg"] or 0))
    # A chunk of one wavelength's legs shares one basis, but too few chunks
    # leave workers idle at the end; aim for ~3 chunks per worker.
    n_legs = len({r["leg"] for r in records}) or 1
    chunk = max(1, min(n_legs, -(-len(records) // (3 * workers))))

    # One BLAS thread per worker: N workers x 4 threads would oversubscribe the
    # cores, and the single-frame search gains nothing from BLAS threads anyway
    # (70-frame sweep, serial: 41.9 s at 1 thread, 42.7 s at 4). Workers inherit
    # os.environ at spawn; holo's own cap keeps an explicitly set value. Agg
    # because a worker has no GUI to draw into.
    knobs = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
             "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MPLBACKEND")
    saved = {k: os.environ.get(k) for k in knobs}
    os.environ.update({k: "1" for k in knobs[:-1]}, MPLBACKEND="Agg")
    try:
        ex = ProcessPoolExecutor(
            workers, mp_context=multiprocessing.get_context("spawn"),
            initializer=_worker_init,
            initargs=(dict(frame_kw, proc=worker_proc),))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    try:
        jobs = [records[i] for i in order]
        for i, (res, err) in zip(order, ex.map(_worker_frame, jobs,
                                               chunksize=chunk)):
            if should_stop():
                return
            yield i, res, err
    finally:
        ex.shutdown(wait=True, cancel_futures=True)


# ── the pipeline ─────────────────────────────────────────────────────────────

def process_records(proc, records, *, config, log=_noop_log, load=None,
                    background=None, ref_index=None, multiport_dir=None,
                    use_multiport=True, save=True, show=False,
                    should_stop=lambda: False, workers=1):
    """Reconstruct every record; return one summary row per successful frame.

    proc            a configured HolographyDataProcessor
    records         list of {path, label, leg, wl}
    load            callable(path) -> 2-D array, for reference frames
    background      a single reference applied to every frame (overrides
                    ref_index), or None
    ref_index       {wavelength_nm: path} reference library
    multiport_dir   directory holding MULTIPORT_FMT-named frames; defaults to
                    the processor's data_dir
    workers         processes for the single-frame pass (frames are
                    independent). >1 needs show=False; rows come back in
                    record order either way.
    """
    load = load or proc.load_hologram
    bg_modifier = float(proc.proc_config.get("background_modifier", 1.0))
    if show:
        workers = 1                          # plots can't be shown from a worker

    legs = sorted({r["leg"] for r in records if r["leg"] is not None})
    wls = sorted({int(round(r["wl"])) for r in records})

    mp_frames = {}
    if use_multiport and len(legs) >= 2:
        mp_frames = run_multiport(multiport_dir or proc.data_dir, legs, wls,
                                  config, log)

    val = ((config.get("experiment") or {}).get("validation") or {})
    frame_kw = dict(load=load, background=background, ref_index=ref_index,
                    bg_modifier=bg_modifier, save=save, show=show,
                    sat_level=float(val.get("saturation_level", 65535)),
                    sat_frac_max=float(val.get("max_saturated_fraction", 0.001)))
    rows = {}
    done = 0
    for i, res, err in _frame_results(proc, records, workers, frame_kw, log,
                                      should_stop):
        done += 1
        rec = records[i]
        label, leg, wl = rec["label"], rec["leg"], rec["wl"]
        log(f"[{done}/{len(records)}] {label}  (leg={leg}, {wl} nm)", "INFO")
        if err is not None:
            log(f"  ✗ {label}: {err.strip().splitlines()[-1]}", "ERROR")
            log(err, "DEBUG")
            continue
        try:
            fidelity = float(res["fidelity"])
            powers = [float(p) for p in res["mode_powers"]]
            engine = "single-frame"

            # Keep multiport's answer for this (leg, lambda) only if it wins.
            frame = mp_frames.get((leg, int(round(wl))))
            if frame is not None and float(frame["fidelity"]) > fidelity:
                power = np.abs(frame["decomp"]) ** 2
                total = float(power.sum())
                powers = [float(x) for x in (power / total if total > 0 else power)]
                log(f"  ↑ multiport {float(frame['fidelity']):.4f} beats "
                    f"single-frame {fidelity:.4f}", "OK")
                fidelity = float(frame["fidelity"])
                engine = "multiport"

            if save:
                np.savez(Path(proc.results_dir) / f"{label}_results.npz",
                         mode_decomposition=res["mode_decomposition"],
                         mode_powers=np.asarray(powers),
                         fidelity=fidelity,
                         recovered_field=res["recovered_field_corrected"])

            rows[i] = {"filename": Path(rec["path"]).name,
                       "source": label,
                       "wavelength_nm": int(round(wl)),
                       "fidelity": fidelity,
                       "engine": engine,
                       "saturated": res["saturated"],
                       "mode_powers": powers}
            preview = "  ".join(f"{p*100:.1f}%" for p in powers[:5])
            log(f"  ✓ fidelity {fidelity:.4f} ({engine})  [{preview}]", "OK")
            if res["saturated"]:
                log(f"  ⚠ SATURATED — {res['saturated_fraction']*100:.2f}% of "
                    f"pixels clipped; this fidelity is not a measurement",
                    "WARN")
        except Exception as e:
            import traceback
            log(f"  ✗ {label}: {e}", "ERROR")
            log(traceback.format_exc(), "DEBUG")
    return [rows[i] for i in sorted(rows)]


def write_summary(results_dir, rows, folder=None, log=_noop_log):
    """Write processing_summary.yaml — the file the GUI's Results tab reads."""
    if not rows:
        return None
    results_dir = Path(results_dir)
    try:
        results_dir.mkdir(parents=True, exist_ok=True)
        summary = {"processing_date": datetime.now().isoformat(),
                   "total_processed": len(rows),
                   "results": rows}
        if folder is not None:
            summary["folder"] = str(folder)
        path = results_dir / "processing_summary.yaml"
        path.write_text(yaml.dump(summary, sort_keys=False))
        return path
    except Exception as e:
        log(f"  (couldn't write results summary: {e})", "DEBUG")
        return None
