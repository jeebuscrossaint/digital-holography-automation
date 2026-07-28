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
  5. Basis consolidation  — average those optima across all ports/wavelengths
     (linear fit in lambda for the quadratic phase) and re-decompose, so every
     frame of the sweep shares ONE mode basis. Without this the transfer matrix
     is assembled from mutually incomparable coefficients.

Measured against Caleb Dobias's archived 19-port × 51-wavelength dataset
(``_caleb_ref/10-17-2023-Wavelengths``), using his own parameters and the
23-mode basis: **96.76% ± 0.95%**. The paper reports 98% ± 0.8%, so roughly
1.2 points are still unexplained — see the OPEN DISCREPANCY note in
``__init__``, and do not close the gap by tightening ``butter_wc``.
Single-frame reconstruction reaches ~97% on one frame and cannot produce a
coherent transfer matrix at all.

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
    core_radius, NA, n_eff : fiber params. Defaults are Caleb's published
        values for this dataset (17.5 µm, 0.13, 1.453) -> a 23-mode basis.
    diameter_range : (start, stop) mode-field-diameter scan in px (paper 55–75)
    pol_half : 'left'/'right'/None — for dual-polarisation frames, zero one
        half so only one polarisation's field is reconstructed (paper zeros the
        right half of the image and the left half of the FFT). None = full frame.
    ref_wavelength : wavelength (nm) used to locate the common beam centre.
    """

    def __init__(self, data_dir, legs, wavelengths,
                 filename_fmt="time 0 leg {leg} wavelength {wl}nm.npy",
                 crop_size=512, nfft=128, mode_size=256,
                 core_radius=17.5e-6, NA=0.13, n_eff=1.453,
                 diameter_range=(63, 70), pol_half="right",
                 ref_wavelength=1545, butter_wc=15, sample_limit=32):
        # The defaults describe the PAPER's lantern: core 16.3 µm with NA=0.15
        # gives a 23-mode LP basis, the number that lantern physically supports.
        #
        # The basis size is the key fidelity knob, and it is a trap. Match it to
        # the lantern's real mode count — do NOT raise NA to chase a bigger
        # number. NA=0.17 here yields 30+ modes and ~98% fidelity that is pure
        # OVERFITTING: more basis functions than there are guided modes, so the
        # extra ones absorb noise. For a different fiber, set core_radius/NA
        # from its spec and check how many modes generateModes() returns.
        #
        # THIS RIG's lantern is 7-port (8 modes): core_radius=12e-6, NA=0.11,
        # with crop_size/nfft sized to the Bobcat 320's 256-px frame rather than
        # the 512/128 defaults (which fit the paper's 1024×1280 Lucid frames).
        # pipeline.run_multiport passes those. Validate once real switch data
        # exists.
        #
        # butter_wc=15 and diameter_range=(63,70) are CALEB'S VALUES, read from
        # his own analysis of this dataset
        # (10-17-2023-Wavelengths/wavelengthDecompUpdatedLPModesForOnePolarization
        # CleanupTimeAgain.py: makeButtersworth(Nfft, Nfft//2, Nfft//2, wc=15),
        # startDiameter=63, stopDiameter=70). Do not "improve" them without
        # reading the note below — the obvious improvement is a trap.
        #
        # This code is a VERIFIED reproduction of that analysis. Checked stage
        # by stage against his saved intermediates (10-17-2023-Wavelengths/
        # fftCentroids.pkl, optimizationDataSet.pkl):
        #
        #   carrier centroids      identical to 0.000 px over all 51 wavelengths
        #   interpolated twin      |overlap| = 1.000000, zero L1 difference
        #   mode decomposition     cosine similarity 0.997-0.9998 per frame
        #   mean fidelity          ours 96.76% +/- 0.95%  vs his 96.89% +/- 1.48%
        #
        # Our spread is tighter and the worst frame much better (93.7% vs 81.1%,
        # 0 vs 24 frames under 95%) because of the basis consolidation above.
        #
        # NOTE ON THE PAPER'S 98%: it is NOT reproducible from this dataset with
        # this method — not by us and not by Caleb's own stored run, which also
        # lands at 96.9%. So a ~1.1 point gap exists between his archived 2023
        # analysis and the published figure; where it comes from is unknown
        # (later refinement, different data, different reporting — ask him).
        # Do NOT try to close it here by tuning. Setting butter_wc=4 reaches
        # 98.3% and looks like a fix, but it diverges from the method AND from
        # his results, and it drives the consolidated diameter to the edge of
        # the search range. Fidelity compares the field to its own LP
        # reconstruction, so a narrower passband inflates it by deleting content
        # the basis cannot represent — same failure mode as an oversized basis.
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
        self.butter_wc = butter_wc
        self.sample_limit = sample_limit

        self._center = None        # (row, col) common beam centre
        self._xC = self._yC = None  # fitted carrier centroid vs wavelength index
        self._modes_by_diam = None

    # ── data ─────────────────────────────────────────────────────────────────
    def _load(self, leg, wl):
        a = np.load(self.data_dir / self.fmt.format(leg=leg, wl=wl)).astype(float)
        # Zero-pad so a crop×crop window fits around ANY beam position. The
        # Bobcat frame is small and the beam often sits low/off-centre, which
        # would otherwise make cropArray() return a truncated (non-square)
        # window and crash the DC filter. The padding is identical for every
        # frame, so beam-centre and carrier coordinates stay mutually consistent.
        pad = self.crop // 2
        return np.pad(a, pad, mode="constant")

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
        if len(self.wavelengths) >= 2:
            # Carrier drifts linearly with wavelength (fringe spacing changes);
            # a line fit across wavelengths beats each frame's noisy centroid.
            mx, cx = np.polyfit(idx, cents[:, 0], 1)
            my, cy = np.polyfit(idx, cents[:, 1], 1)
            self._xC = idx * mx + cx
            self._yC = idx * my + cy
        else:
            # Single wavelength: nothing to fit — use the (cross-port-averaged)
            # centroid directly. np.polyfit(deg=1) needs >=2 points and errors.
            self._xC = cents[:, 0].copy()
            self._yC = cents[:, 1].copy()
        return self._xC, self._yC

    # ── step 3: sub-pixel field extraction for one frame ────────────────────────
    def extract_field(self, leg, wl_index):
        c = cropArray(self._load(leg, self.wavelengths[wl_index]).astype(float),
                      self._center, self.crop)
        fft = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(c)))
        interp, _, _ = fourier_interp_2d(
            fft, self.nfft, self.nfft, self.sample_limit,
            offset=(self._xC[wl_index] - self.crop // 2,
                    self._yC[wl_index] - self.crop // 2))
        interp = interp * makeButterworth(self.nfft, self.nfft // 2, self.nfft // 2,
                                          wc=self.butter_wc)
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

    def decompose_frame(self, leg, wl_index, diameter, phase, offset):
        """Decompose one frame with GIVEN parameters — no per-frame search.

        The counterpart to ``reconstruct_frame``: same field extraction, but the
        mode-field diameter, quadratic phase and x/y offset are handed in, so
        every frame is expressed in the same basis."""
        mbd = self._modes()
        diameter = int(np.clip(diameter, 0, mbd.shape[0] - 1))
        field = self.extract_field(leg, wl_index)
        adj = adjustField(field, phase, offset[0], offset[1])
        decomp, recomp = decompAndRecomp(adj, mbd[diameter])
        fid = float(np.real(np.square(np.abs(overlap2FieldsV2(recomp, adj)))))
        return {"fidelity": fid, "decomp": decomp, "recomp": recomp, "field": adj,
                "diameter": diameter, "phase": float(phase),
                "offset": (int(offset[0]), int(offset[1]))}

    def consolidate_parameters(self, per_frame):
        """Collapse per-frame optima into one basis shared by the whole sweep.

        Paper, Sec. 2: "optimal parameters were averaged across all SM ports and
        wavelengths ... except for the quadratic phase mask, which instead used a
        linear fit to address the wavelength dependency."

        The reason is physical, not cosmetic. The mode-field diameter and the
        field position are properties of the imaging setup — they do not change
        from port to port — so their per-frame scatter is fit noise and gets
        averaged away. Defocus genuinely does track wavelength, so the quadratic
        phase factor k is fit linearly in lambda rather than averaged flat.

        Returns ``(diameter, (x_offset, y_offset), phase_of_wl_index)``.
        """
        values = list(per_frame.values())
        diameter = int(round(float(np.mean([r["diameter"] for r in values]))))
        xo = int(round(float(np.mean([r["offset"][0] for r in values]))))
        yo = int(round(float(np.mean([r["offset"][1] for r in values]))))

        idx, phases = [], []
        for wi in range(len(self.wavelengths)):
            at_wl = [r["phase"] for (_leg, w), r in per_frame.items() if w == wi]
            if at_wl:
                idx.append(wi)
                phases.append(float(np.mean(at_wl)))
        if len(idx) >= 2:
            slope, intercept = np.polyfit(idx, phases, 1)
            def phase_of(wi):
                return float(wi * slope + intercept)
        else:
            constant = phases[0] if phases else 0.0
            def phase_of(_wi):
                return constant
        return diameter, (xo, yo), phase_of

    # ── full sweep → transfer matrices ──────────────────────────────────────────
    def reconstruct_all(self, progress=None, consistent_basis=True):
        """Reconstruct every (leg, wavelength). Returns dict with:
        transfer_matrices [n_wl][n_mode, n_leg], fidelity [n_wl, n_leg],
        and the per-frame results. ``progress`` is an optional callback(str).

        With ``consistent_basis`` (the paper's procedure, and the default) the
        sweep is reconstructed twice: once to find each frame's optimum, then
        again with those optima consolidated by ``consolidate_parameters`` so
        every frame shares one basis. This matters because the transfer matrix
        is assembled ACROSS frames — coefficients measured against per-frame
        bases are not mutually comparable, so the columns of an unconsolidated
        TM do not describe one physical lantern. Individual fidelities dip
        slightly (each frame is no longer separately maximised); the TM is what
        becomes trustworthy.

        Pass ``consistent_basis=False`` to get the raw per-frame optima — useful
        for reporting the best achievable single-frame fidelity, not for a TM.
        """
        if self._xC is None:
            self.fit_carrier_centroids()
        nL, nW = len(self.legs), len(self.wavelengths)
        n_mode = self._modes().shape[1]

        # Pass 1 — per-frame optimisation.
        per_frame = {}
        for wi in range(nW):
            for leg in self.legs:
                r = self.reconstruct_frame(leg, wi)
                per_frame[(leg, wi)] = r
                if progress:
                    progress(f"λ={self.wavelengths[wi]}nm leg={leg} "
                             f"fidelity={r['fidelity']*100:.1f}%")

        params = None
        if consistent_basis and per_frame:
            diameter, offset, phase_of = self.consolidate_parameters(per_frame)
            params = {"diameter": diameter, "offset": offset}
            if progress:
                progress(f"consolidating basis: diameter={diameter} "
                         f"offset={offset} (phase linear in λ)")
            # Pass 2 — re-decompose every frame on the shared basis.
            for (leg, wi) in list(per_frame):
                per_frame[(leg, wi)] = self.decompose_frame(
                    leg, wi, diameter, phase_of(wi), offset)

        TM = np.zeros((nW, n_mode, nL), dtype=np.complex128)
        fid = np.zeros((nW, nL))
        frames = {}
        for wi in range(nW):
            for li, leg in enumerate(self.legs):
                r = per_frame[(leg, wi)]
                TM[wi, :, li] = r["decomp"]
                fid[wi, li] = r["fidelity"]
                frames[(leg, self.wavelengths[wi])] = r

        return {"transfer_matrices": TM, "fidelity": fid, "frames": frames,
                "legs": self.legs, "wavelengths": self.wavelengths,
                "carrier_x": self._xC, "carrier_y": self._yC,
                "basis": params}
