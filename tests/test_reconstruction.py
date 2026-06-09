# -*- coding: utf-8 -*-
"""Golden-file regression test for the hologram reconstruction.

The reconstruction is a deterministic grid search (no randomness), so a real
captured hologram always reconstructs to the same fidelity. This pins that
output: if a future refactor silently breaks the math — the way the old
np.sqrt(intensity) bug drove fidelity to 0.000, or the carrier-edge slice bug
could have — this test fails loudly instead of shipping wrong physics.

Fixture: tests/fixtures/sample_hologram.npy — a real Bobcat 320 frame
(snapshot_20260604_204225), 256x320 uint16.
"""

import numpy as np
import pytest

from conftest import FIXTURES

# Pinned against the committed fixture + locked deps (uv.lock). If this changes,
# it should be because someone INTENDED to change the reconstruction — update
# the constant in the same commit and say why.
# 2026-06-09: 0.9186 -> 0.9770 after widening the crop window (crop_size
# 100 -> 200): the old 100-px window cropped the mode's outer structure off and
# capped fidelity (Caleb's "still very zoomed in"). Bigger window captures the
# full field. Grid 100 -> 200 to match.
GOLDEN_FIDELITY = 0.9770
FIDELITY_TOL    = 0.02      # absolute; FP/platform slack, still catches real breaks
GRID            = 200       # processor's reconstruction grid size (= crop_size)


@pytest.fixture(scope="module")
def result():
    from data_processing import HolographyDataProcessor
    proc = HolographyDataProcessor()
    holo = np.load(FIXTURES / "sample_hologram.npy")
    return proc.process_single_hologram(
        holo, wavelength_nm=1550, show_plots=False, save_plots=False)


def test_fidelity_matches_golden(result):
    fid = float(result["fidelity"])
    assert abs(fid - GOLDEN_FIDELITY) < FIDELITY_TOL, (
        f"reconstruction fidelity {fid:.4f} drifted from golden "
        f"{GOLDEN_FIDELITY} (tol {FIDELITY_TOL}) — the pipeline changed")


def test_fidelity_is_physical(result):
    # A real off-axis hologram must reconstruct well above chance. This is the
    # catch-all for catastrophic regressions (e.g. fidelity collapsing to ~0).
    assert 0.85 < float(result["fidelity"]) <= 1.0


def test_result_shape_and_keys(result):
    for key in ("fidelity", "mode_powers", "mode_decomposition",
                "reconstructed_field", "recovered_field_corrected", "best_params"):
        assert key in result, f"missing result key: {key}"
    assert result["reconstructed_field"].shape == (GRID, GRID)


def test_mode_powers_normalized(result):
    mp = np.asarray(result["mode_powers"])
    assert mp.ndim == 1 and mp.size > 0
    assert np.all(mp >= 0)
    assert abs(float(mp.sum()) - 1.0) < 1e-6   # powers are a normalized distribution
