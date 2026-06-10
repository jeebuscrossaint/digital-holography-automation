# -*- coding: utf-8 -*-
"""Generate the per-frame 'key figure' Caleb asked for — the full reconstruction
breakdown in one image:

  1 original hologram   2 FFT (+carrier)   3 FFT selection (demod+Butterworth)
  4 iFFT recovered field (amp+phase)       5 iFFT + corrections (phase + bg)
  6 recomposition (with fidelity)          7 LP01 mode (reference)

Usage:
    uv run python tools/key_figure.py 1550
    uv run python tools/key_figure.py 1550 --no-bg
Reads holography_data/leg01-wavelength{wl}.npy (+ references/ for background)
and writes holography_data/processed_results/key_figure_{wl}nm.png.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")
import numpy as np
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
from data_processing import HolographyDataProcessor, _butter_lp        # noqa: E402
from calebsUsefulFunctions import normalizeIntensity, pltBoth          # noqa: E402


def make(wl: int, use_bg: bool = True, bg_modifier: float = 0.8):
    data = ROOT / "holography_data" / f"leg01-wavelength{wl}.npy"
    ref  = ROOT / "holography_data" / "references" / f"leg01-wavelength{wl}.npy"
    holo = np.load(data).astype(float)
    background = np.load(ref).astype(float) if (use_bg and ref.exists()) else None

    proc = HolographyDataProcessor()
    res = proc.process_single_hologram(holo, wavelength_nm=wl,
                                       background=background, bg_modifier=bg_modifier)
    lp = res["best_params"]["lp"]
    modes, grid = proc._opt_modes, proc._grid

    # rebuild FFT stages on the (bg-subtracted) square-cropped frame, for display
    H = holo - bg_modifier * background if background is not None else holo
    h, w = H.shape; s = min(h, w)
    H = H[(h - s) // 2:(h - s) // 2 + s, (w - s) // 2:(w - s) // 2 + s]
    N = H.shape[0]; c = N // 2
    P = np.abs(np.fft.fftshift(np.fft.fft2(H)))
    yy, xx = np.ogrid[:N, :N]; Pm = P.copy(); Pm[np.hypot(yy - c, xx - c) <= 18] = 0
    py, px = np.unravel_index(int(Pm.argmax()), Pm.shape)
    u0, v0 = (px - c) / N, (py - c) / N
    Y, X = np.mgrid[0:N, 0:N]
    Sd = np.fft.fftshift(np.fft.fft2(H * np.exp(-2j * np.pi * (u0 * X + v0 * Y)))) * _butter_lp(N, lp, 4)
    ES = np.fft.ifft2(np.fft.ifftshift(Sd))
    recovered = normalizeIntensity(proc._center_on_beam(ES, grid))

    fig = plt.figure(figsize=(16, 8))
    ax = plt.subplot(2, 4, 1); ax.imshow(H, cmap="gray"); ax.set_title("1. Original hologram"); ax.axis("off")
    ax = plt.subplot(2, 4, 2); ax.imshow(np.log10(P + 1), cmap="magma"); ax.plot(px, py, "cx", ms=10)
    ax.set_title("2. FFT (log) + carrier"); ax.axis("off")
    ax = plt.subplot(2, 4, 3); ax.imshow(np.log10(np.abs(Sd) + 1), cmap="magma")
    ax.set_title("3. FFT selection (demod + Butterworth)"); ax.axis("off")
    plt.subplot(2, 4, 4); pltBoth(recovered); plt.title("4. iFFT recovered field (amp+phase)")
    plt.subplot(2, 4, 5); pltBoth(res["recovered_field_corrected"])
    plt.title("5. iFFT + corrections (phase" + (" + bg)" if background is not None else ")"))
    plt.subplot(2, 4, 6); pltBoth(res["reconstructed_field"])
    plt.title(f"6. Recomposition  (fidelity {res['fidelity']*100:.1f}%)")
    plt.subplot(2, 4, 7); pltBoth(modes[0]); plt.title("7. LP01 mode (reference)")
    plt.tight_layout()
    out = ROOT / "holography_data" / "processed_results" / f"key_figure_{wl}nm.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=140)
    print(f"saved {out}  (fidelity {res['fidelity']*100:.1f}%, grid {grid})")
    return out


if __name__ == "__main__":
    wl = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].lstrip("-").isdigit() else 1550
    make(wl, use_bg="--no-bg" not in sys.argv)
