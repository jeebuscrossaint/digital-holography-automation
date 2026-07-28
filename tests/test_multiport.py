# -*- coding: utf-8 -*-
"""Validation test for the multi-port (paper-fidelity) reconstruction.

The heavy end-to-end test runs only when Caleb's archived dataset is present
(it's gitignored / multi-GB, so it won't exist in CI or a fresh clone). When it
does run, it confirms the cross-port + sub-pixel pipeline reconstructs a real
frame well ABOVE the ~92% single-frame ceiling, and — where Caleb's saved
intermediates are also present — that our field recovery reproduces his exactly.
"""

from pathlib import Path

import pytest

ROOT  = Path(__file__).resolve().parent.parent
CALEB = ROOT / "_caleb_ref" / "10-17-2023-Wavelengths"
# Caleb's saved intermediates, from the shared 002_Holography archive. Present
# only if that folder has been pulled (rclone); the tests using it auto-skip.
CALEB_OUT = ROOT / "002_Holography_full" / "10-17-2023-Wavelengths"
CENTROIDS = CALEB_OUT / "fftCentroids.pkl"


def test_module_imports():
    import multiport_reconstruction as m
    assert hasattr(m, "MultiPortReconstructor")


@pytest.mark.skipif(not CALEB.exists(),
                    reason="Caleb reference dataset not present (gitignored, multi-GB)")
def test_multiport_beats_single_frame():
    from multiport_reconstruction import MultiPortReconstructor
    # A few wavelengths near 1575 nm keeps the carrier fit fast; all 19 legs so
    # the cross-port averaging is real.
    R = MultiPortReconstructor(data_dir=CALEB, legs=range(19),
                               wavelengths=[1565, 1570, 1575])
    assert R._modes().shape[1] == 23, "tuned basis should be the 23 modes the lantern supports"
    R.fit_carrier_centroids()
    r = R.reconstruct_frame(leg=10, wl_index=2)          # 1575 nm
    assert r["fidelity"] > 0.95, (
        f"multi-port fidelity {r['fidelity']:.3f} should clear the tuned ~97% range "
        f"(well above the single-frame ~92% ceiling) — the path may be broken")


@pytest.mark.skipif(not CALEB.exists(),
                    reason="Caleb reference dataset not present (gitignored, multi-GB)")
def test_consolidated_basis_matches_measured_fidelity():
    """Pin where this pipeline actually sits on the paper's own data.

    With Caleb's parameters (butter_wc=15, diameter 63-70, 23-mode basis) the
    measured mean over 3 wavelengths x 19 legs is ~96.8%. The paper reports
    98% +/- 0.8%, so this is deliberately pinned to the number we GET, not the
    number we want. Caleb's own stored run on this data gives 96.89%, so this
    IS the faithful result — see the verification note in
    multiport_reconstruction and CLAUDE.md.

    If this rises because the twin passband was narrowed, that is the metric
    being gamed, not a fix.
    """
    from multiport_reconstruction import MultiPortReconstructor
    R = MultiPortReconstructor(data_dir=CALEB, legs=range(19),
                               wavelengths=[1525, 1550, 1575])
    out = R.reconstruct_all(consistent_basis=True)
    fid = out["fidelity"]
    assert 0.955 < fid.mean() < 0.985, (
        f"mean fidelity {fid.mean()*100:.2f}% left the measured 96.8% band — "
        f"either the pipeline regressed, or the open gap was closed (good, but "
        f"update this test and the discrepancy note together)")
    assert fid.min() > 0.90, f"worst frame {fid.min()*100:.2f}% is unphysically low"
    # The TM must be one coherent object: (n_wl, n_mode, n_leg).
    assert out["transfer_matrices"].shape == (3, 23, 19)
    assert out["basis"] is not None, "consolidated run must report its shared basis"


@pytest.mark.skipif(not CALEB.exists(),
                    reason="Caleb reference dataset not present (gitignored, multi-GB)")
def test_default_params_match_calebs_published_analysis():
    """The defaults must stay the values Caleb actually used on this dataset.

    Read from 10-17-2023-Wavelengths/wavelengthDecompUpdatedLPModesForOne
    PolarizationCleanupTimeAgain.py. They are easy to 'tune' into a better
    fidelity number and thereby stop reproducing the paper's method.
    """
    from multiport_reconstruction import MultiPortReconstructor
    R = MultiPortReconstructor(data_dir=CALEB, legs=[0], wavelengths=[1550])
    assert R.butter_wc == 15
    assert R.diameter_range == (63, 70)
    assert (R.crop, R.nfft, R.mode_size) == (512, 128, 256)
    assert R.sample_limit == 32
    assert (R.core_radius, R.NA, R.n_eff) == (17.5e-6, 0.13, 1.453)
    # Whatever the fiber spec, the basis must be the 23 modes the paper reports.
    assert R._modes().shape[1] == 23


@pytest.mark.skipif(not (CALEB.exists() and CENTROIDS.exists()),
                    reason="Caleb's raw dataset + saved intermediates not present")
def test_field_recovery_matches_calebs_saved_intermediates():
    """Field recovery must stay bit-identical to Caleb's own run.

    His fftCentroids.pkl holds the cross-port carrier fit and the interpolated
    twin image for every (wavelength, leg). Steps 1-3 of this pipeline
    reproduce both exactly, which is what lets us say a fidelity difference
    lives in the decomposition rather than in the optics maths.
    """
    import pickle
    import numpy as np
    from multiport_reconstruction import MultiPortReconstructor
    from calebsUsefulFunctions import (fourier_interp_2d, makeButterworth,
                                       cropArray, overlap2FieldsV2)

    with open(CENTROIDS, "rb") as f:
        interp_his, xC_his, yC_his = pickle.load(f)

    wls = list(range(1525, 1576))
    R = MultiPortReconstructor(data_dir=CALEB, legs=range(19), wavelengths=wls)
    R.fit_carrier_centroids()

    # Carrier fit: same to well under a hundredth of a pixel.
    assert np.abs(np.asarray(R._xC) - xC_his).max() < 1e-6
    assert np.abs(np.asarray(R._yC) - yC_his).max() < 1e-6

    # Interpolated twin image: same complex array.
    wi, leg = 25, 5                                    # 1550 nm, mid-range leg
    crop = cropArray(R._load(leg, wls[wi]).astype(float), R._center, R.crop)
    fft = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(crop)))
    ours, _, _ = fourier_interp_2d(
        fft, R.nfft, R.nfft, R.sample_limit,
        offset=(R._xC[wi] - R.crop // 2, R._yC[wi] - R.crop // 2))
    ours = ours * makeButterworth(R.nfft, R.nfft // 2, R.nfft // 2, wc=R.butter_wc)
    assert abs(overlap2FieldsV2(ours, interp_his[wi, leg])) > 1 - 1e-9
