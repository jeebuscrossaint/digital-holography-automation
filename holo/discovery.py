# -*- coding: utf-8 -*-
"""Turn a folder of arbitrary hologram files into records the engines accept.

This is library code, not CLI code: "point at a folder and figure out what is
in it" is useful to the GUI's Process button as much as to ``holo process``.
It was previously buried in ``process.py`` where only the CLI could reach it.

    records = discovery.stage(folder, default_wl=1550)
    #  -> [{"path": Path, "label": str, "leg": int, "wl": float}, ...]

Handles 16-bit images without clipping (never ``Image.convert('L')`` -- that
truncates to 8 bits and saturates the frame, which makes the intensity
nonlinear in the field and corrupts both amplitude and phase).
"""

import re
from pathlib import Path

import numpy as np
import yaml

IMG_EXT = (".png", ".tif", ".tiff")
ARR_EXT = (".npy", ".npz")
ALL_EXT = ARR_EXT + IMG_EXT          # priority order for dedupe

# The canonical layout both engines expect.
MULTIPORT_FMT = "leg{leg:02d}-wavelength{wl:04d}.npy"


# ── loading ──────────────────────────────────────────────────────────────────

def _to_2d_real(arr):
    arr = np.asarray(arr)
    if np.iscomplexobj(arr):
        arr = np.abs(arr)
    arr = np.squeeze(arr)
    if arr.ndim == 3:                   # RGB(A) -> mean over channels
        arr = arr[..., :3].mean(axis=-1)
    return np.nan_to_num(arr.astype(np.float64))


def load_frame(path):
    """Load one hologram from .npy/.npz/.png/.tif as a 2-D float array."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".npy":
        return _to_2d_real(np.load(path))
    if ext == ".npz":
        z = np.load(path)
        for k in ("hologram", "frame", "data", "image"):
            if k in z:
                return _to_2d_real(z[k])
        for v in z.values():
            a = _to_2d_real(v)
            if a.ndim == 2:
                return a
        raise ValueError(f"no 2-D array in {path.name}")
    from PIL import Image                # 16-bit safe (no convert('L'))
    return _to_2d_real(Image.open(path))


# ── parsing leg / wavelength out of a filename ───────────────────────────────

def _wl_from_name(stem):
    m = re.search(r"w(?:ave)?l(?:ength)?[\s_-]?(\d{3,4})", stem, re.I)
    return float(m.group(1)) if m else None


def _leg_from_name(stem):
    m = re.search(r"leg[\s_-]?(\d+)", stem, re.I) or re.search(r"(\d+)\s*$", stem)
    return int(m.group(1)) if m else None


def resolve_wavelength(path, default):
    """Wavelength for a frame: a .yaml sidecar wins, then the filename."""
    path = Path(path)
    side = path.with_suffix(".yaml")
    if side.exists():
        try:
            meta = yaml.safe_load(side.read_text()) or {}
            if "wavelength_nm" in meta:
                return float(meta["wavelength_nm"])
        except (OSError, yaml.YAMLError):
            pass
    return _wl_from_name(path.stem) or float(default)


def discover(folder, default_wl=1550):
    """Sorted records {src, label, leg, wl} -- one per (leg, wavelength),
    preferring .npy/.npz over an image of the same frame.

    The key must include the wavelength: a sweep stores many wavelengths per
    leg, and keying on the leg alone silently keeps only one of them (that bug
    would have processed 19 of 969 frames on the paper's grid, with nothing to
    indicate it -- pinned by tests/test_process_discovery.py).
    """
    folder = Path(folder)
    best = {}
    for f in sorted(folder.iterdir()):
        if f.is_dir() or f.suffix.lower() not in ALL_EXT:
            continue
        leg = _leg_from_name(f.stem)
        wl = resolve_wavelength(f, default_wl)
        key = (f"leg{leg:02d}" if leg is not None else f.stem, round(wl, 4))
        cur = best.get(key)
        if cur is None or ALL_EXT.index(f.suffix.lower()) < ALL_EXT.index(cur.suffix.lower()):
            best[key] = f
    records, auto = [], 0
    for (_key, wl), f in sorted(best.items()):
        leg = _leg_from_name(f.stem)
        if leg is None:
            auto += 1
            leg = auto
        records.append({"src": f, "label": f.stem, "leg": leg, "wl": wl})
    return records


def stage(folder, default_wl=1550, cache_name=".holo_cache"):
    """Discover a folder and normalize every frame into the canonical
    leg x lambda .npy layout both engines expect.

    Returns (records, cache_dir). The cache is safe to delete; it is
    regenerated on demand.
    """
    folder = Path(folder)
    found = discover(folder, default_wl)
    if not found:
        return [], None

    cache = folder / cache_name
    cache.mkdir(exist_ok=True)
    records = []
    for r in found:
        wl_i = int(round(r["wl"]))
        npy = cache / MULTIPORT_FMT.format(leg=r["leg"], wl=wl_i)
        np.save(npy, load_frame(r["src"]))
        records.append({"path": npy, "label": r["label"],
                        "leg": r["leg"], "wl": r["wl"]})
    records.sort(key=lambda r: (r["leg"], r["wl"]))
    return records, cache


def build_ref_index(source, config=None):
    """Background references: ``(index {wl: path}, single_array_or_None)``.

    An explicit file applies to every frame; a folder is indexed by wavelength
    and matched per frame. ``source=None`` falls back to the config's
    ``processing.background_dir`` when background subtraction is enabled.
    """
    src = source
    if src is None and config is not None:
        pcfg = (config.get("processing") or {})
        if pcfg.get("subtract_background") and pcfg.get("background_dir"):
            src = pcfg["background_dir"]
    if src is None:
        return {}, None

    p = Path(src)
    if p.is_file():
        return {}, load_frame(p)
    if p.is_dir():
        idx = {}
        for rp in sorted(p.iterdir()):
            if rp.suffix.lower() in ALL_EXT:
                w = _wl_from_name(rp.stem)
                if w is not None:
                    idx[w] = rp
        return idx, None
    return {}, None
