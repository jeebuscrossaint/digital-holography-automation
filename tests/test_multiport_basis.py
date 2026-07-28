# -*- coding: utf-8 -*-
"""Basis consistency for the assembled transfer matrix.

A transfer matrix is built ACROSS frames, so every frame must be decomposed in
the same LP-mode basis for its columns to describe one physical lantern. The
paper reaches that by averaging the per-frame optima (mode-field diameter and
field position) over all ports and wavelengths, and linear-fitting the
quadratic-phase factor against wavelength.

These tests use the consolidation logic directly with synthetic per-frame
results — no dataset needed, so they run everywhere.
"""

import numpy as np
import pytest

from multiport_reconstruction import MultiPortReconstructor


@pytest.fixture
def reconstructor(tmp_path):
    # Never loads a frame: only consolidate_parameters is exercised.
    return MultiPortReconstructor(tmp_path, legs=[1, 2, 3],
                                  wavelengths=[1525, 1550, 1575])


def _frames(diameters, phases, offsets):
    """Build a {(leg, wl_index): result} map from per-frame parameter lists."""
    out = {}
    for i, (leg, wi) in enumerate([(l, w) for w in range(3) for l in (1, 2, 3)]):
        out[(leg, wi)] = {"diameter": diameters[i], "phase": phases[i],
                          "offset": offsets[i], "fidelity": 0.9}
    return out


def test_diameter_and_offset_are_averaged(reconstructor):
    # Scatter around 20 / (2, -3): the setup's real values, plus fit noise.
    diameters = [19, 20, 21, 20, 19, 21, 20, 20, 20]
    offsets = [(2, -3), (3, -3), (1, -3), (2, -2), (2, -4),
               (2, -3), (3, -3), (1, -3), (2, -3)]
    params = reconstructor.consolidate_parameters(
        _frames(diameters, [0.0] * 9, offsets))
    diameter, offset, _phase_of = params
    assert diameter == 20
    assert offset == (2, -3)


def test_quadratic_phase_is_linear_in_wavelength(reconstructor):
    # Defocus really does track wavelength, so the phase factor is fit, not
    # averaged. Per-wavelength means here are 0.1 / 0.2 / 0.3.
    phases = [0.09, 0.10, 0.11, 0.19, 0.20, 0.21, 0.29, 0.30, 0.31]
    _d, _o, phase_of = reconstructor.consolidate_parameters(
        _frames([20] * 9, phases, [(0, 0)] * 9))
    assert phase_of(0) == pytest.approx(0.10, abs=1e-6)
    assert phase_of(1) == pytest.approx(0.20, abs=1e-6)
    assert phase_of(2) == pytest.approx(0.30, abs=1e-6)
    # A flat average would give 0.20 everywhere and lose the trend.
    assert phase_of(2) - phase_of(0) == pytest.approx(0.20, abs=1e-6)


def test_single_wavelength_needs_no_fit(tmp_path):
    # np.polyfit(deg=1) needs >= 2 points; one wavelength must not raise.
    r = MultiPortReconstructor(tmp_path, legs=[1, 2], wavelengths=[1550])
    per_frame = {(1, 0): {"diameter": 20, "phase": 0.4, "offset": (1, 1),
                          "fidelity": 0.9},
                 (2, 0): {"diameter": 22, "phase": 0.6, "offset": (1, 1),
                          "fidelity": 0.9}}
    diameter, offset, phase_of = r.consolidate_parameters(per_frame)
    assert diameter == 21
    assert offset == (1, 1)
    assert phase_of(0) == pytest.approx(0.5)


def test_decompose_frame_clamps_diameter_index(tmp_path, monkeypatch):
    """An averaged diameter must stay inside the generated mode stack."""
    r = MultiPortReconstructor(tmp_path, legs=[1], wavelengths=[1550], nfft=8)
    stack = np.zeros((3, 2, 8, 8))          # 3 diameters, 2 modes, 8x8
    stack[:, 0] = 1.0                       # flat mode
    stack[:, 1, :4] = 1.0                   # half-plane mode (non-degenerate)
    monkeypatch.setattr(r, "_modes", lambda: stack)
    monkeypatch.setattr(r, "extract_field",
                        lambda leg, wi: np.ones((8, 8), dtype=complex))
    for requested, expected in ((99, 2), (-5, 0), (1, 1)):
        assert r.decompose_frame(1, 0, requested, 0.0, (0, 0))["diameter"] == expected
