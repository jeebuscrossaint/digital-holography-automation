# -*- coding: utf-8 -*-
"""Multi-port transfer-matrix reconstruction (Dobias et al., Opt. Express 2026).

This is the *high-fidelity* path used in the paper, distinct from the
single-frame reconstruction in ``data_processing.py`` (which tops out ~92%
because it can only see one hologram at a time). The extra accuracy here comes
from information that only exists across a FULL leg × wavelength sweep:

  1. Beam centring  — overlay all ports at a reference wavelength to find the
     common field centre, and crop every frame around it.
  2. Carrier centroid by CROSS-PORT AVERAGING  — at each wavelength, sum the
     off-axis sideband over all ports (the carrier is set by the optics and is
     common to every port; only the signal differs), find that averaged
     centroid, then LINEAR-FIT the centroid vs wavelength. This pins the
     carrier far more precisely than any single frame's center-of-mass.
  3. Sub-pixel twin extraction  — ``fourier_interp_2d`` (Fourier fine-binning,
     Ransom 2002) resamples the sideband centred on the fitted carrier, so the
     demodulation leaves no residual phase ramp.
  4. Per-frame refinement  — iterate mode-field diameter, quadratic-phase
     factor, and x/y offset to maximise the LP-mode overlap (fidelity).

Validated against Caleb Dobias's archived 19-port × 51-wavelength dataset:
reproduces ~95% mean fidelity (vs ~92% single-frame), 93–97% per frame.

Ready for the new fiber switch: point it at a leg×wavelength sweep directory
and it returns per-(port, wavelength) fidelity, mode decomposition, and the
assembled transfer matrices.
"""

import sys
from pathlib import Path

import numpy as np
import scipy

_ROOT = Path(__file__).parent
_lib = str(_ROOT / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from calebsUsefulFunctions import (  # noqa: E402
    generateMask, cropArray, filterDCComponents, makeButterworth,
    fourier_interp_2d, generateModesByDiameter, adjustField, findBestDiameter,
    findBestPhase, findBestOffset, decompAndRecomp, overlap2FieldsV2,
)


def _argmax2d(field):
    """Integer (row, col) of the array maximum — Caleb's ``getCenterOfMass``
    (misnamed in his lib; it's an argmax, used on already-blurred arrays)."""
    return np.unravel_index(np.argmax(field), field.shape)


class MultiPortReconstructor:
    """Reconstruct a photonic-lantern transfer matrix from a leg × wavelength
    hologram sweep using the paper's cross-port, sub-pixel method.

    Parameters
    ----------
    data_dir : path to the directory of .npy frames
    legs, wavelengths : the sweep axes (wavelengths in nm)
    filename_fmt : format string with ``{leg}`` and ``{wl}`` fields, e.g.
        ``"time 0 leg {leg} wavelength {wl}nm.npy"`` (Caleb's archive) or
        ``"leg{leg:02d}-wavelength{wl:04d}.npy"`` (this app's collector).
    crop_size, nfft : working FFT sizes (paper: 512 crop, 128 interp grid)
    core_radius, NA, n_eff : fiber params (paper: 16.3 µm, 0.13, 1.453)
    diameter_range : (start, stop) mode-field-diameter scan in px (paper 55–75)
    pol_half : 'left'/'right'/None — for dual-polarisation frames, zero one
        half so only one polarisation's field is reconstructed (paper zeros the
        right half of the image and the left half of the FFT). None = full frame.
    ref_wavelength : wavelength (nm) used to locate the common beam centre.
    """

    def __init__(self, data_dir, legs, wavelengths,
                 filename_fmt="time 0 leg {leg} wavelength {wl}nm.npy",
                 crop_size=512, nfft=128, mode_size=256,
                 core_radius=16.3e-6, NA=0.13, n_eff=1.453,
                 diameter_range=(55, 75), pol_half="right",
                 ref_wavelength=1545):
        self.data_dir = Path(data_dir)
        self.legs = list(legs)
        self.wavelengths = list(wavelengths)
        self.fmt = filename_fmt
        self.crop = crop_size
        self.nfft = nfft
        self.mode_size = mode_size
        self.core_radius = core_radius
        self.NA = NA
        self.n_eff = n_eff
        self.diameter_range = diameter_range
        self.pol_half = pol_half
        self.ref_wl = ref_wavelength

        self._center = None        # (row, col) common beam centre
        self._xC = self._yC = None  # fitted carrier centroid vs wavelength index
        self._modes_by_diam = None

    # ── data ─────────────────────────────────────────────────────────────────
    def _load(self, leg, wl):
        return np.load(self.data_dir / self.fmt.format(leg=leg, wl=wl))

    def _zero_image_half(self, a):
        if self.pol_half == "right":
            a = a.copy(); a[:, a.shape[1] // 2:] = 0
        elif self.pol_half == "left":
            a = a.copy(); a[:, :a.shape[1] // 2] = 0
        return a

    def _zero_fft_half(self, f):
        # keep one sideband (mirror of the zeroed image half)
        if self.pol_half == "right":
            f = f.copy(); f[:, :f.shape[0] // 2] = 0
        elif self.pol_half == "left":
            f = f.copy(); f[:, f.shape[0] // 2:] = 0
        return f

    # ── step 1: common beam centre ─────────────────────────────────────────────
    def find_beam_center(self):
        tot = None
        for leg in self.legs:
            frame = np.log10(self._load(leg, self.ref_wl).astype(float) + 1)
            tot = frame if tot is None else tot + frame
        tot = self._zero_image_half(tot)
        conv = scipy.signal.fftconvolve(tot, generateMask(self.mode_size, self.mode_size),
                                        mode="same")
        self._center = _argmax2d(conv)
        return self._center

    # ── step 2: cross-port carrier centroid + linear fit vs wavelength ──────────
    def fit_carrier_centroids(self):
        if self._center is None:
            self.find_beam_center()
        cents = np.zeros((len(self.wavelengths), 2))
        for i, wl in enumerate(self.wavelengths):
            fa = np.zeros((self.crop, self.crop))
            for leg in self.legs:
                c = cropArray(self._load(leg, wl).astype(float), self._center, self.crop)
                f = filterDCComponents(np.fft.fftshift(np.fft.fft2(c)), 1, 40)
                f = self._zero_fft_half(f)
                fa = fa + np.abs(f)
            fc = scipy.signal.convolve2d(fa, generateMask(15, 15), mode="same")
            pk = _argmax2d(fc)
            bf = makeButterworth(self.crop, pk[1], pk[0])
            cents[i] = scipy.ndimage.center_of_mass(fc * bf)
        idx = np.arange(len(self.wavelengths))
        mx, cx = np.polyfit(idx, cents[:, 0], 1)
        my, cy = np.polyfit(idx, cents[:, 1], 1)
        self._xC = idx * mx + cx
        self._yC = idx * my + cy
        return self._xC, self._yC

    # ── step 3: sub-pixel field extraction for one frame ────────────────────────
    def extract_field(self, leg, wl_index):
        c = cropArray(self._load(leg, self.wavelengths[wl_index]).astype(float),
                      self._center, self.crop)
        fft = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(c)))
        interp, _, _ = fourier_interp_2d(
            fft, self.nfft, self.nfft, 32,
            offset=(self._xC[wl_index] - self.crop // 2,
                    self._yC[wl_index] - self.crop // 2))
        interp = interp * makeButterworth(self.nfft, self.nfft // 2, self.nfft // 2, wc=15)
        return np.fft.ifftshift(np.fft.ifft2(np.fft.fftshift(interp)))

    # ── step 4: per-frame optimisation → fidelity + decomposition ───────────────
    def _modes(self):
        if self._modes_by_diam is None:
            d0, d1 = self.diameter_range
            self._modes_by_diam = generateModesByDiameter(
                d0, d1, 1, self.nfft, self.core_radius, self.NA,
                self.wavelengths[-1] * 1e-9, self.n_eff)
        return self._modes_by_diam

    def reconstruct_frame(self, leg, wl_index, max_iter=10):
        """Return dict(fidelity, decomp, recomp, field, diameter, phase, offset)
        for one (leg, wavelength) frame."""
        mbd = self._modes()
        field = self.extract_field(leg, wl_index)
        pf, xo, yo, prev = -0.5, 0, 0, -1.0
        diam = 0
        for _ in range(max_iter):
            adj = adjustField(field, pf, xo, yo)
            diam = findBestDiameter(adj, mbd)
            adj0 = adjustField(field, 0, xo, yo)
            pf = findBestPhase(adj0, mbd[diam], start=pf - .05, stop=pf + .05, step=.01)
            adj = adjustField(field, pf, 0, 0)
            xo, yo = findBestOffset(adj, mbd[diam], xstart=xo - 3, xstop=xo + 3,
                                    ystart=yo - 3, ystop=yo + 3)
            adj = adjustField(field, pf, xo, yo)
            _, recomp = decompAndRecomp(adj, mbd[diam])
            fid = float(np.real(np.square(np.abs(overlap2FieldsV2(recomp, adj)))))
            if fid == prev:
                break
            prev = fid
        adj = adjustField(field, pf, xo, yo)
        decomp, recomp = decompAndRecomp(adj, mbd[diam])
        fid = float(np.real(np.square(np.abs(overlap2FieldsV2(recomp, adj)))))
        return {"fidelity": fid, "decomp": decomp, "recomp": recomp, "field": adj,
                "diameter": int(diam), "phase": float(pf), "offset": (int(xo), int(yo))}

    # ── full sweep → transfer matrices ──────────────────────────────────────────
    def reconstruct_all(self, progress=None):
        """Reconstruct every (leg, wavelength). Returns dict with:
        transfer_matrices [n_wl][n_mode, n_leg], fidelity [n_wl, n_leg],
        and the per-frame results. ``progress`` is an optional callback(str)."""
        if self._xC is None:
            self.fit_carrier_centroids()
        nL, nW = len(self.legs), len(self.wavelengths)
        n_mode = self._modes().shape[1]
        TM = np.zeros((nW, n_mode, nL), dtype=np.complex128)
        fid = np.zeros((nW, nL))
        frames = {}
        for wi in range(nW):
            for li, leg in enumerate(self.legs):
                r = self.reconstruct_frame(leg, wi)
                TM[wi, :, li] = r["decomp"]
                fid[wi, li] = r["fidelity"]
                frames[(leg, self.wavelengths[wi])] = r
                if progress:
                    progress(f"λ={self.wavelengths[wi]}nm leg={leg} "
                             f"fidelity={r['fidelity']*100:.1f}%")
        return {"transfer_matrices": TM, "fidelity": fid, "frames": frames,
                "legs": self.legs, "wavelengths": self.wavelengths,
                "carrier_x": self._xC, "carrier_y": self._yC}
