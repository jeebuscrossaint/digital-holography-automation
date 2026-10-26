# -*- coding: utf-8 -*-
"""The single-frame search screens its (cutoff, FOV, phase) grid with a
closed-form fidelity and evaluates only the near-best combinations exactly.
That must choose exactly what evaluating every combination would: this pins it
against the exhaustive loop on the real fixture frame."""

import contextlib
import io

import numpy as np
import pytest

from conftest import FIXTURES


def _exhaustive(proc, hologram, wl_nm):
    """The search as it was before screening: every combination, exactly."""
    from holo.lib.calebsUsefulFunctions import (
        combinedOutput, generatePhaseMask, modeDecomp, normalizeIntensity,
        overlap2FieldsV2)
    h, w = hologram.shape
    s = min(h, w)
    H = hologram[(h - s) // 2:(h - s) // 2 + s, (w - s) // 2:(w - s) // 2 + s]
    grid = proc._grid
    best = None
    for lp in proc._lp_cuts:
        ES_full, _, _ = proc._recover_field(H, lp)
        base = normalizeIntensity(proc._center_on_beam(ES_full, grid))
        for fov in proc._fovs:
            modes = proc._modes_at(fov, wl_nm * 1e-9)
            nm = min(proc._num_modes, modes.shape[0])
            for pf in proc._phases:
                fld = normalizeIntensity(base * generatePhaseMask(grid, pf))
                dec = modeDecomp(fld, modes, nm)
                fid = abs(overlap2FieldsV2(fld, combinedOutput(modes[:nm], dec))) ** 2
                if best is None or fid > best[0]:
                    best = (fid, lp, fov, float(pf))
    return best


@pytest.mark.parametrize("core_radius", [1.7e-5, 1.2e-5])   # 15/17- and 8-mode
def test_screened_search_matches_exhaustive(core_radius):
    from holo.data_processing import HolographyDataProcessor
    proc = HolographyDataProcessor()
    proc._core_radius = core_radius
    holo = np.load(FIXTURES / "sample_hologram.npy").astype(float)
    with contextlib.redirect_stdout(io.StringIO()):
        res = proc.process_single_hologram(holo, wavelength_nm=1550)
        want = _exhaustive(proc, holo, 1550)
    got = res["best_params"]
    assert (got["lp"], got["fov"], got["phase"]) == want[1:]
    # Position refinement only ever replaces the search's best with a better fit.
    assert res["fidelity"] >= want[0]
