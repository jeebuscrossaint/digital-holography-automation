# -*- coding: utf-8 -*-
"""
process.py — the one-and-done, headless twin of the GUI "Process" button.

    python process.py <folder> [<folder> ...]

Point it at ANY folder of holograms and it just works:
  • auto-detects .png / .tif / .npy / .npz frames (16-bit safe — no clipping)
  • figures out leg + wavelength from filenames / sidecars
  • runs the SAME pipeline the GUI runs: single-frame reconstruction, plus
    multiport cross-port reconstruction on multi-leg datasets, keeping the
    better of the two per frame
  • optional nearest-wavelength background subtraction
  • writes the 8-panel analysis figures + .npz results + processing_summary.yaml
    into <folder>/processed_results/

It does NOT modify any analysis code — it only calls it. To let both engines
read arbitrary inputs, frames are normalized once into <folder>/.holo_cache/
as leg{NN}-wavelength{NNNN}.npy (safe to delete; regenerated on demand).

Options:
    --wavelength NM    fallback wavelength when a frame has none (default 1550)
    --config PATH      config template (default experiment_config.yaml)
    --background PATH  reference file or folder (overrides config background_dir)
    --show             also display plots interactively
    --no-save          just print fidelities; write nothing
    --single           force single-frame only (skip multiport)
"""
import sys
import re
import argparse
from pathlib import Path
from datetime import datetime

import numpy as np
import yaml

_ROOT = Path(__file__).resolve().parent
for _p in (_ROOT, _ROOT / 'lib'):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from data_processing import HolographyDataProcessor  # noqa: E402

_IMG_EXT = ('.png', '.tif', '.tiff')
_ARR_EXT = ('.npy', '.npz')
_ALL_EXT = _ARR_EXT + _IMG_EXT          # priority order for dedupe


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
    ext = path.suffix.lower()
    if ext == '.npy':
        return _to_2d_real(np.load(path))
    if ext == '.npz':
        z = np.load(path)
        for k in ('hologram', 'frame', 'data', 'image'):
            if k in z:
                return _to_2d_real(z[k])
        for v in z.values():
            a = _to_2d_real(v)
            if a.ndim == 2:
                return a
        raise ValueError(f'no 2-D array in {path.name}')
    from PIL import Image                # 16-bit safe (no convert('L'))
    return _to_2d_real(Image.open(path))


# ── discovery: one record per leg, with (leg, wavelength) ─────────────────────
def _wl_from_name(stem):
    m = re.search(r'w(?:ave)?l(?:ength)?[\s_-]?(\d{3,4})', stem, re.I)
    return float(m.group(1)) if m else None


def _leg_from_name(stem):
    m = re.search(r'leg[\s_-]?(\d+)', stem, re.I) or re.search(r'(\d+)\s*$', stem)
    return int(m.group(1)) if m else None


def resolve_wavelength(path, default):
    side = path.with_suffix('.yaml')
    if side.exists():
        try:
            meta = yaml.safe_load(side.read_text()) or {}
            if 'wavelength_nm' in meta:
                return float(meta['wavelength_nm'])
        except Exception:
            pass
    return _wl_from_name(path.stem) or float(default)


def discover(folder, default_wl):
    """Return sorted list of records: {src, label, leg, wl}. One frame per leg
    (prefers .npy/.npz over images on a clash); enumerates legs with no number."""
    best = {}
    for f in sorted(folder.iterdir()):
        if f.is_dir() or f.suffix.lower() not in _ALL_EXT:
            continue
        leg = _leg_from_name(f.stem)
        key = f'leg{leg:02d}' if leg is not None else f.stem
        cur = best.get(key)
        if cur is None or _ALL_EXT.index(f.suffix.lower()) < _ALL_EXT.index(cur.suffix.lower()):
            best[key] = f
    records, auto = [], 0
    for key, f in sorted(best.items()):
        leg = _leg_from_name(f.stem)
        if leg is None:
            auto += 1
            leg = auto
        records.append({'src': f, 'label': f.stem, 'leg': leg,
                        'wl': resolve_wavelength(f, default_wl)})
    return records


# ── background (nearest wavelength within 2 nm, like the GUI) ─────────────────
def build_ref_index(bg_arg, config):
    """Return (ref_index: {wl: path}, single: array-or-None). --background wins
    over config; a file applies to all frames, a folder is indexed by λ."""
    src = bg_arg
    if src is None:
        pcfg = config.get('processing', {})
        if pcfg.get('subtract_background') and pcfg.get('background_dir'):
            src = pcfg['background_dir']
    if src is None:
        return {}, None
    p = Path(src)
    if p.is_file():
        return {}, load_frame(p)
    if p.is_dir():
        idx = {}
        for rp in sorted(p.iterdir()):
            if rp.suffix.lower() in _ALL_EXT:
                w = _wl_from_name(rp.stem)
                if w is not None:
                    idx[w] = rp
        return idx, None
    return {}, None


# ── main per-folder run ───────────────────────────────────────────────────────
def process_folder(folder, args, config):
    folder = Path(folder)
    if not folder.is_dir():
        print(f'[{folder}] not a folder — skipping')
        return
    records = discover(folder, args.wavelength)
    if not records:
        print(f'[{folder}] no holograms found — skipping')
        return

    # Normalize every input into the canonical leg×λ .npy both engines expect.
    cache = folder / '.holo_cache'
    cache.mkdir(exist_ok=True)
    staged = {}                          # (leg, wl_int) -> {npy, label}
    for r in records:
        wl_i = int(round(r['wl']))
        npy = cache / f"leg{r['leg']:02d}-wavelength{wl_i:04d}.npy"
        np.save(npy, load_frame(r['src']))
        staged[(r['leg'], wl_i)] = {'npy': npy, 'label': r['label']}

    proc = HolographyDataProcessor(config_file=args.config)
    proc.data_dir = cache
    proc.results_dir = folder / 'processed_results'
    if not args.no_save:
        proc.results_dir.mkdir(parents=True, exist_ok=True)
    bg_mod = float(proc.proc_config.get('background_modifier', 1.0))
    ref_index, single_bg = build_ref_index(args.background, config)

    legs = sorted({leg for leg, _ in staged})
    wls = sorted({wl for _, wl in staged})
    print('=' * 60)
    print(f'{folder}  —  {len(staged)} frames, {len(legs)} legs, {len(wls)} wavelengths')
    print('=' * 60)

    # Multiport (cross-port) reconstruction on multi-leg datasets, exactly as
    # the GUI: run it once, then keep it per frame only if it beats single-frame.
    mp_frames = {}
    if len(legs) >= 2 and not args.single:
        print(f'Multi-leg ({len(legs)} legs) — attempting multiport reconstruction…')
        try:
            from multiport_reconstruction import MultiPortReconstructor
            mp = MultiPortReconstructor(
                cache, legs, wls,
                filename_fmt='leg{leg:02d}-wavelength{wl:04d}.npy',
                crop_size=200, nfft=64, mode_size=180,
                core_radius=12e-6, NA=0.11, n_eff=1.453,
                diameter_range=(40, 90), pol_half=None,
                ref_wavelength=wls[0])
            mp_out = mp.reconstruct_all()
            mp_frames = mp_out.get('frames', {})
            print(f'  multiport mean fidelity {float(np.mean(mp_out["fidelity"])):.3f} '
                  f'— keeping better of multiport/single-frame per frame')
        except Exception as e:
            print(f'  multiport unavailable ({e}) — single-frame only')

    summary = []
    for i, ((leg, wl), info) in enumerate(sorted(staged.items()), 1):
        label = info['label']
        print(f'\n[{i}/{len(staged)}] {label}  (leg={leg}, {wl} nm)')
        try:
            hologram = proc.load_hologram(info['npy'])
            bg = single_bg
            if bg is None and ref_index:
                nearest = min(ref_index, key=lambda w: abs(w - wl))
                if abs(nearest - wl) <= 2.0:
                    bg = load_frame(ref_index[nearest])
            res = proc.process_single_hologram(
                hologram, wavelength_nm=wl, show_plots=args.show,
                save_plots=not args.no_save, plot_prefix=label,
                background=bg, bg_modifier=bg_mod)

            fid = float(res['fidelity'])
            powers = [float(p) for p in res['mode_powers']]
            engine = 'single-frame'
            fr = mp_frames.get((leg, wl))
            if fr is not None and float(fr['fidelity']) > fid:
                dp = np.abs(fr['decomp']) ** 2
                s = float(dp.sum())
                powers = [float(x) for x in (dp / s if s > 0 else dp)]
                fid = float(fr['fidelity'])
                engine = 'multiport'
            if not args.no_save:
                np.savez(proc.results_dir / f'{label}_results.npz',
                         mode_decomposition=res['mode_decomposition'],
                         mode_powers=np.asarray(powers),
                         fidelity=fid,
                         recovered_field=res['recovered_field_corrected'])
            summary.append({'filename': info['npy'].name, 'source': label,
                            'wavelength_nm': int(wl), 'fidelity': fid,
                            'engine': engine, 'mode_powers': powers})
            print(f'  [ok] fidelity {fid:.4f} ({engine})')
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f'  [error] {label}: {e}')

    if summary and not args.no_save:
        (proc.results_dir / 'processing_summary.yaml').write_text(
            yaml.dump({'processing_date': datetime.now().isoformat(),
                       'folder': str(folder),
                       'total_processed': len(summary),
                       'results': summary}, sort_keys=False))
    if summary:
        mean = sum(r['fidelity'] for r in summary) / len(summary)
        print(f'\n{folder}: mean fidelity {mean:.3f} over {len(summary)} frames')
        if not args.no_save:
            print(f'  -> {proc.results_dir}')


def main():
    ap = argparse.ArgumentParser(description='One-and-done holography analysis on a folder.')
    ap.add_argument('folders', nargs='+', help='folder(s) of holograms')
    ap.add_argument('--wavelength', type=float, default=1550)
    ap.add_argument('--config', default=str(_ROOT / 'experiment_config.yaml'))
    ap.add_argument('--background', default=None)
    ap.add_argument('--show', action='store_true')
    ap.add_argument('--no-save', action='store_true')
    ap.add_argument('--single', action='store_true')
    args = ap.parse_args()
    config = yaml.safe_load(Path(args.config).read_text())
    for folder in args.folders:
        process_folder(folder, args, config)


if __name__ == '__main__':
    main()
