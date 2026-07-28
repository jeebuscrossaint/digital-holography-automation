# -*- coding: utf-8 -*-
"""Validation test for the multi-port (paper-fidelity) reconstruction.

The heavy end-to-end test runs only when Caleb's archived dataset is present
(it's gitignored / multi-GB, so it won't exist in CI or a fresh clone). When it
does run, it confirms the cross-port + sub-pixel pipeline reconstructs a real
frame well ABOVE the ~92% single-frame ceiling — i.e. that the method that
closes the paper's fidelity gap is wired up correctly.
"""

from pathlib import Path

import pytest

ROOT  = Path(__file__).resolve().parent.parent
CALEB = ROOT / "_caleb_ref" / "10-17-2023-Wavelengths"


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
    number we want — see the OPEN DISCREPANCY note in multiport_reconstruction.

    If someone closes the gap for real, this floor should rise and the note
    should go. If it rises because the twin passband was narrowed, that is the
    metric being gamed, not a fix.
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
