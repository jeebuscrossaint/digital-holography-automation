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
