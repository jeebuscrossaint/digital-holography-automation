# -*- coding: utf-8 -*-
"""Acquisition: drive the laser, grab frames, write them to disk.

Library code, like ``discovery`` is library code. "Sweep the wavelength and
save N exposures" is as useful to ``holo acquire`` as to the GUI's Start
button, and neither front end should own it.

    from holo import acquisition
    acquisition.sweep(camera, laser, [1530, 1531, ...], out, repeats=3)

Manual-bench mode is the default: no fiber switch, no paddle motors. You
connect the leg and set the paddles by hand, then sweep. Pass ``leg=`` to
label the frames with whichever leg is plugged in.

**Repeats go in per-repeat subfolders** (``rep01/``, ``rep02/``, ...), not in
one folder with a suffix. ``discovery.discover`` keeps exactly one file per
(leg, wavelength), so three exposures written side by side in one folder would
leave two of them silently unprocessed. One folder per repeat means each is a
complete sweep that ``holo process`` / ``holo tm`` can read as-is.
"""

import re
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

from .fringe_detection import check_fringes_visible, check_saturation


# ── naming and sidecars ──────────────────────────────────────────────────────

def format_capture_name(fmt: str, leg, wl) -> str:
    """Build a save filename that tolerates fractional wavelengths.

    Whole-number wavelengths use the configured format verbatim (e.g.
    ``leg01-wavelength1525.npy`` — unchanged/backward compatible). A fractional
    wavelength would crash the default ``{wavelength:04d}`` integer code, so we
    fall back to a dot-free tag (``leg01-wavelength1525p1.npy``) — the 'p' keeps
    the file extension clean. The true wavelength is always stored in the .yaml
    metadata, so the filename is just a label."""
    leg = int(leg)
    try:
        return fmt.format(leg=leg,
                          wavelength=int(wl) if float(wl).is_integer() else wl)
    except (ValueError, KeyError):
        safe = re.sub(r"\{wavelength[^}]*\}", "{wavelength}", fmt)
        tag = f"{float(wl):.4f}".rstrip("0").rstrip(".").replace(".", "p")
        return safe.format(leg=leg, wavelength=tag)


def read_paddle_angles(motors):
    """Actual paddle positions read from the hardware. Deliberately not
    motors.angles — that is the last *commanded* angle, which is stale
    ([0,0,0]) if the app hasn't moved the paddles this session, and it would
    be recorded into the capture metadata as if it were measured."""
    if motors is None:
        return [0.0, 0.0, 0.0]
    out = []
    for i in (1, 2, 3):
        try:
            out.append(round(float(motors.getPosition(i)), 2))
        except Exception:
            try:
                out.append(round(float(motors.angles[i - 1]), 2))
            except Exception:
                out.append(0.0)
    return out


def save_preview_png(frame, path):
    """Save a viewable 8-bit PNG of a raw frame (mean ± 3σ contrast stretch)."""
    try:
        from PIL import Image
        a = np.asarray(frame).astype(np.float32)
        mu, sd = float(a.mean()), float(a.std())
        if sd < 1e-6:
            disp = np.full(a.shape, 128, np.uint8)
        else:
            lo, hi = mu - 3 * sd, mu + 3 * sd
            disp = np.clip((a - lo) / max(hi - lo, 1e-6) * 255, 0, 255).astype(np.uint8)
        Image.fromarray(disp, "L").save(str(path))
    except Exception:
        pass


DEFAULT_FMT = "leg{leg:02d}-wavelength{wavelength:04d}.npy"


def repeat_dir(out, rep: int, repeats: int) -> Path:
    """Where repeat ``rep`` (1-based) of ``repeats`` is written.

    A single exposure per wavelength writes straight into ``out`` — the layout
    the GUI has always produced. More than one gets ``out/repNN`` so each
    repeat is a self-contained sweep.
    """
    out = Path(out)
    return out if repeats <= 1 else out / f"rep{rep:02d}"


# ── one frame ────────────────────────────────────────────────────────────────

def save_capture(frame, folder, leg, wl, *, fmt=DEFAULT_FMT, motors=None,
                 sat_level=65535, sat_frac_max=0.001, extra=None,
                 preview=True, metadata=True):
    """Write one frame plus its .png preview and .yaml sidecar.

    Returns the record dict: path, wavelength, saturation verdict. The frame is
    saved even when it is saturated — losing raw data is worse than having a
    flagged frame — but the sidecar marks it invalid, because clipping makes
    intensity nonlinear in the field and corrupts amplitude *and* phase.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    sat = check_saturation(frame, sat_level=sat_level,
                           sat_fraction_max=sat_frac_max)

    path = folder / format_capture_name(fmt, leg, wl)
    np.save(path, frame)
    if preview:
        save_preview_png(frame, path.with_suffix(".png"))

    if metadata:
        angles = read_paddle_angles(motors)
        meta = {"leg": int(leg), "wavelength_nm": float(wl),
                "timestamp": datetime.now().isoformat(),
                "polarizer_angles_deg": angles,
                "motor_angles": angles,              # back-compat key
                "saturated": bool(sat["saturated"]),
                "saturated_fraction": float(sat["fraction"]),
                "max_value": int(sat["max_value"]),
                "fill_fraction": float(sat["fill_fraction"])}
        if extra:
            meta.update(extra)
        with open(path.with_suffix(".yaml"), "w") as f:
            yaml.dump(meta, f)

    return {"path": path, "leg": int(leg), "wl": float(wl),
            "saturated": bool(sat["saturated"]),
            "saturated_fraction": float(sat["fraction"]),
            "max_value": int(sat["max_value"]),
            "fill_fraction": float(sat["fill_fraction"])}


# ── the sweep ────────────────────────────────────────────────────────────────

def set_wavelength(laser, wl, dwell=0.5):
    """Command a wavelength, wait for the laser to settle, read back what it
    actually tuned to.

    The readback is the point: the HP 8168E accepts a command and queues an
    error rather than raising, so a rejected ``:WAVE`` leaves the laser sitting
    at the previous wavelength while the loop happily labels the frame with the
    one it asked for. Returns the measured nm, or None if it can't be read.
    """
    if laser is None:
        return None
    laser.changeWavelength(wl)
    time.sleep(dwell)
    try:
        actual = float(laser.checkWavelength())
    except (ValueError, TypeError, AttributeError):
        return None
    return actual


def sweep(camera, laser, wavelengths, out, *, leg=1, repeats=1, motors=None,
          fmt=DEFAULT_FMT, dwell=0.5, settle=0.0, exposure=None,
          sat_level=65535, sat_frac_max=0.001, fringe_method=None,
          wl_tolerance=0.05, log=print, should_stop=None, on_frame=None):
    """Sweep ``wavelengths``, saving ``repeats`` exposures at each one.

    The repeats are taken back to back at a fixed wavelength — that is what
    makes them a repeatability measurement rather than three separate sweeps.
    Each lands in its own ``repNN`` folder (see module docstring).

    Args:
        camera:      object with ``getFrame()`` (holo.hardware.XenicsCam.xCam)
        laser:       object with ``changeWavelength()``; None = don't tune
        wavelengths: nm values to visit, in order
        out:         output folder
        leg:         leg label written into filenames and metadata
        repeats:     exposures per wavelength
        dwell:       seconds to wait after commanding a wavelength
        settle:      extra seconds between the repeats at one wavelength
        exposure:    integration time (µs) to apply before starting
        fringe_method: if set, report the fringe metric per frame (no motor
                     optimisation — paddles are the operator's job here)
        wl_tolerance: warn if the laser's readback is off by more than this (nm)
        should_stop: callable checked between frames; True aborts cleanly
        on_frame:    callable(frame, record) for live display

    Returns a list of the per-frame record dicts that were saved.
    """
    out = Path(out)
    wavelengths = list(wavelengths)
    repeats = max(1, int(repeats))
    total = len(wavelengths) * repeats
    stop = should_stop or (lambda: False)
    rows = []

    if camera is None:
        raise ValueError("no camera — cannot acquire")

    if exposure is not None:
        try:
            actual = camera.setExposure(exposure)
            log(f"Exposure set to {actual:.0f} us")
        except Exception as e:
            log(f"WARN  could not set exposure: {e}")

    if laser is not None:
        try:
            laser.outputState(True)
            time.sleep(0.3)
            if "1" in str(laser.isOutputOn()):
                log("Laser output ON")
            else:
                log("WARN  laser would NOT confirm ON — this run may capture "
                    "dark frames; check the laser before walking away")
        except Exception as e:
            log(f"WARN  could not enable laser output: {e}")
    else:
        log("No laser — every frame will be taken at the current wavelength")

    log(f"Sweep: {len(wavelengths)} wavelengths x {repeats} exposures "
        f"= {total} frames, leg {leg} -> {out}")

    n = 0
    saturated = 0
    for wl in wavelengths:
        if stop():
            break
        actual = set_wavelength(laser, wl, dwell)
        if actual is not None and abs(actual - float(wl)) > wl_tolerance:
            log(f"WARN  asked for {wl} nm, laser reports {actual:.3f} nm")
        err = getattr(laser, "last_error", None) if laser is not None else None
        if err:
            log(f"WARN  laser: {err}")
            laser.last_error = None

        for rep in range(1, repeats + 1):
            if stop():
                break
            if settle and rep > 1:
                time.sleep(settle)

            frame = camera.getFrame()
            n += 1
            if frame is None:
                log(f"[{n}/{total}] {wl} nm rep {rep}  FRAME CAPTURE FAILED "
                    f"— skipping")
                continue

            rec = save_capture(frame, repeat_dir(out, rep, repeats), leg, wl,
                               fmt=fmt, motors=motors, sat_level=sat_level,
                               sat_frac_max=sat_frac_max,
                               extra={"repeat": rep, "repeats": repeats,
                                      "wavelength_commanded_nm": float(wl),
                                      "wavelength_measured_nm": actual})
            rows.append(rec)

            note = ""
            if fringe_method:
                try:
                    _ok, metric = check_fringes_visible(frame, fringe_method, 0)
                    note = f"  fringe {metric:.3f}"
                except Exception:
                    pass
            if rec["saturated"]:
                saturated += 1
                note += (f"  SATURATED {rec['saturated_fraction']*100:.2f}% "
                         f"clipped (max {rec['max_value']}) — data INVALID, "
                         f"reduce exposure or laser power")
            try:
                shown = rec["path"].relative_to(out)
            except ValueError:
                shown = rec["path"].name
            log(f"[{n}/{total}] {wl} nm rep {rep} -> {shown}{note}")

            if on_frame is not None:
                on_frame(frame, rec)

    log(f"Done — {len(rows)} frames saved to {out}"
        + (f"; {saturated} SATURATED and unusable" if saturated else ""))
    return rows


def plan(wavelengths, out, *, leg=1, repeats=1, fmt=DEFAULT_FMT):
    """The files a sweep would write, without touching hardware. Lets you check
    the layout and the wavelength list before committing bench time."""
    wavelengths = list(wavelengths)
    repeats = max(1, int(repeats))
    return [repeat_dir(out, rep, repeats) / format_capture_name(fmt, leg, wl)
            for wl in wavelengths
            for rep in range(1, repeats + 1)]
