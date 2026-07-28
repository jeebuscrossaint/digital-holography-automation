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
    from multiport_reconstruction import MultiPortReconstructor

    # Fiber parameters for the multiport basis. NOTE these are deliberately a
    # separate config block from `processing.core_radius` (which sizes the
    # single-frame basis) because the two currently disagree about the same
    # physical lantern — see CLAUDE.md, "Known physics discrepancy".
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
            diameter_range=(40, 90),
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


# ── the pipeline ─────────────────────────────────────────────────────────────

def process_records(proc, records, *, config, log=_noop_log, load=None,
                    background=None, ref_index=None, multiport_dir=None,
                    use_multiport=True, save=True, show=False,
                    should_stop=lambda: False):
    """Reconstruct every record; return one summary row per successful frame.

    proc            a configured HolographyDataProcessor
    records         list of {path, label, leg, wl}
    load            callable(path) -> 2-D array, for reference frames
    background      a single reference applied to every frame (overrides
                    ref_index), or None
    ref_index       {wavelength_nm: path} reference library
    multiport_dir   directory holding MULTIPORT_FMT-named frames; defaults to
                    the processor's data_dir
    """
    load = load or proc.load_hologram
    bg_modifier = float(proc.proc_config.get("background_modifier", 1.0))

    legs = sorted({r["leg"] for r in records if r["leg"] is not None})
    wls = sorted({int(round(r["wl"])) for r in records})

    mp_frames = {}
    if use_multiport and len(legs) >= 2:
        mp_frames = run_multiport(multiport_dir or proc.data_dir, legs, wls,
                                  config, log)

    rows = []
    for i, rec in enumerate(records, 1):
        if should_stop():
            break
        label, leg, wl = rec["label"], rec["leg"], rec["wl"]
        log(f"[{i}/{len(records)}] {label}  (leg={leg}, {wl} nm)", "INFO")
        try:
            hologram = proc.load_hologram(rec["path"])
            bg = background
            if bg is None:
                bg = nearest_background(ref_index, wl, load, log)

            res = proc.process_single_hologram(
                hologram, wavelength_nm=wl, show_plots=show, save_plots=save,
                plot_prefix=label, background=bg, bg_modifier=bg_modifier)

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

            rows.append({"filename": Path(rec["path"]).name,
                         "source": label,
                         "wavelength_nm": int(round(wl)),
                         "fidelity": fidelity,
                         "engine": engine,
                         "mode_powers": powers})
            preview = "  ".join(f"{p*100:.1f}%" for p in powers[:5])
            log(f"  ✓ fidelity {fidelity:.4f} ({engine})  [{preview}]", "OK")
        except Exception as e:
            import traceback
            log(f"  ✗ {label}: {e}", "ERROR")
            log(traceback.format_exc(), "DEBUG")
    return rows


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
