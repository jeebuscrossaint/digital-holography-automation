"""Dev harness: implement the Optics Express reconstruction and measure
fidelity on the real snapshots, iterating params. Not shipped — scratch pad.

Method (Dobias et al., Opt. Express 2026, Sec. 2):
  FFT the raw hologram INTENSITY -> isolate twin sideband (sub-pixel center)
  -> Butterworth low-pass -> IFFT -> complex field ES -> remove quadratic
  phase (defocus) -> LP-mode decomposition -> fidelity = |<ERec,ES>|^2.
"""
import sys, glob, os
import numpy as np
import scipy.ndimage as ndi
sys.path[:0] = ['.', 'lib']
from calebsUsefulFunctions import (generateModes, normalizeIntensity,
                                   modeDecomp, combinedOutput, overlap2FieldsV2,
                                   generatePhaseMask)


def butter_lp(N, D0, order=4):
    y, x = np.ogrid[:N, :N]
    r = np.hypot(y - N // 2, x - N // 2)
    return 1.0 / (1.0 + (r / D0) ** (2 * order))


def recover_field(H, lp_cut=30, lp_order=4, dc_radius=18):
    """Off-axis recovery: FFT intensity, find carrier sub-pixel, demodulate,
    Butterworth low-pass, IFFT -> complex field."""
    H = H.astype(float)
    N = H.shape[0]
    F = np.fft.fftshift(np.fft.fft2(H))
    P = np.abs(F)
    cy, cx = N // 2, N // 2
    yy, xx = np.ogrid[:N, :N]
    Pm = P.copy()
    Pm[np.hypot(yy - cy, xx - cx) <= dc_radius] = 0      # kill DC to find carrier
    py, px = np.unravel_index(int(Pm.argmax()), Pm.shape)
    w = 6                                                 # sub-pixel refine
    sub = Pm[py - w:py + w + 1, px - w:px + w + 1]
    dy, dx = ndi.center_of_mass(sub)
    cyy, cxx = py - w + dy, px - w + dx
    u0, v0 = (cxx - cx) / N, (cyy - cy) / N              # carrier freq (cyc/px)
    Y, X = np.mgrid[0:N, 0:N]
    demod = H * np.exp(-2j * np.pi * (u0 * X + v0 * Y))   # twin -> DC
    Sd = np.fft.fftshift(np.fft.fft2(demod)) * butter_lp(N, lp_cut, lp_order)
    return np.fft.ifft2(np.fft.ifftshift(Sd))


def center_crop_on_beam(ES, size):
    mag = np.abs(ES) ** 2
    cy, cx = ndi.center_of_mass(mag)
    cy, cx = int(round(cy)), int(round(cx))
    N = ES.shape[0]
    y0 = min(max(cy - size // 2, 0), N - size)
    x0 = min(max(cx - size // 2, 0), N - size)
    return ES[y0:y0 + size, x0:x0 + size]


def fidelity(field, modes, num_modes):
    dec = modeDecomp(field, modes, num_modes)
    rec = combinedOutput(modes[:num_modes], dec)
    return abs(overlap2FieldsV2(field, rec)) ** 2, dec


GRID = 100
NUM_MODES = 18
# mode bases at a range of effective FOVs (sets mode-field diameter on the grid)
FOVS = [round(v, 7) for v in np.arange(20e-6, 90e-6, 8e-6)]
PHASES = np.arange(-3, 3.01, 0.5)
LP_CUTS = [22, 30, 40]

mode_cache = {}
def get_modes(fov):
    if fov not in mode_cache:
        m = generateModes(N=GRID, pxz=fov / GRID, coreRadius=17e-6, NA=0.11,
                          wavelength=1.55e-6, rIndex=1.453)
        mode_cache[fov] = m
    return mode_cache[fov]


def best_for(H):
    overall = (0, None)
    for lp in LP_CUTS:
        ES = recover_field(H, lp_cut=lp)
        fld0 = normalizeIntensity(center_crop_on_beam(ES, GRID))
        for fov in FOVS:
            modes = get_modes(fov)
            nm = min(NUM_MODES, modes.shape[0])
            for pf in PHASES:
                fld = normalizeIntensity(fld0 * generatePhaseMask(GRID, pf))
                fid, _ = fidelity(fld, modes, nm)
                if fid > overall[0]:
                    overall = (round(float(fid), 3),
                               dict(lp=lp, fov=fov, phase=round(float(pf), 2), nm=nm))
    return overall


if __name__ == '__main__':
    for f in sorted(glob.glob('holography_data/snapshot_*.npy')):
        H = np.load(f)
        s = min(H.shape); H = H[:s, :s]
        fid, params = best_for(H)
        print(f'{os.path.basename(f)}: fidelity={fid}  {params}')
