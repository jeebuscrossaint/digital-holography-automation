# -*- coding: utf-8 -*-
"""GET_LP_mode is the hot spot of mode generation (~70% of a single-frame
reconstruction), so it was optimized to evaluate each Bessel function only
in its own region and once per distinct radius. That must not change a single
bit: these tests pin it against the original whole-grid implementation."""

import numpy as np
import pytest
from scipy.special import jv, kv

from holo.lib.MMF import GET_LP_mode, MMF


def _reference_lp_mode(X, Y, order, u, w, coreRadius):
    """The original implementation, kept verbatim as the oracle."""
    dx = abs(X[0, 0] - X[0, 1])
    dy = abs(Y[0, 1] - Y[1, 1])
    angle, rad = np.arctan2(Y, X), np.sqrt(X**2 + Y**2)
    modeCos = np.zeros_like(X)
    modeSin = np.zeros_like(X)
    cosTerm = np.cos(order * angle)
    sinTerm = np.sin(order * angle)
    coreBessel = jv(order, (u / coreRadius) * rad) / jv(order, u)
    claddingBessel = kv(order, (w / coreRadius) * rad) / kv(order, w)
    inCore = rad <= coreRadius
    inCladding = rad > coreRadius
    modeCos[inCore] = coreBessel[inCore] * cosTerm[inCore]
    modeSin[inCore] = coreBessel[inCore] * sinTerm[inCore]
    modeCos[inCladding] = claddingBessel[inCladding] * cosTerm[inCladding]
    modeSin[inCladding] = claddingBessel[inCladding] * sinTerm[inCladding]
    normCos = np.sqrt(np.sum(modeCos**2) * dx * dy)
    normSin = np.sqrt(np.sum(modeSin**2) * dx * dy)
    modeCos /= normCos if normCos != 0 else 1
    modeSin /= normSin if normSin != 0 else 1
    return np.nan_to_num(modeCos), np.nan_to_num(modeSin)


# This rig's 8-mode basis (core 12 um, NA 0.11) at the FOV extremes the
# single-frame optimizer scans, plus the paper's 23-mode lantern.
@pytest.mark.parametrize("core, NA, fov, wl", [
    (12e-6, 0.11, 20e-6, 1525e-9),
    (12e-6, 0.11, 120e-6, 1575e-9),
    (17.5e-6, 0.13, 60e-6, 1550e-9),
])
def test_lp_modes_bit_identical_to_reference(core, NA, fov, wl):
    N = 200
    fiber = MMF(core, NA, fov / N, N)
    # Mode parameters exactly as modes2 solves them.
    k = 2 * np.pi / wl
    V = core * NA * k
    for order, u in ((0, 0.6 * V), (1, 0.5 * V), (3, 0.9 * V)):
        w = np.sqrt(V**2 - u**2)
        got = GET_LP_mode(fiber.XX, fiber.YY, order, u, w, core)
        want = _reference_lp_mode(fiber.XX, fiber.YY, order, u, w, core)
        for g, r in zip(got, want):
            assert np.array_equal(g, r)
