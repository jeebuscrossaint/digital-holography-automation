# -*- coding: utf-8 -*-
"""Unit tests for fringe_detection — saturation rejection and the carrier
prominence metric the polarization optimizer maximizes. All synthetic, so no
hardware or captured data is needed and they run in milliseconds."""

import numpy as np

from fringe_detection import (calculate_sideband_energy, check_saturation,
                              calculate_sideband_balance)


def _fringes(size=256, fx=10, fy=5):
    """A clean off-axis cosine fringe pattern (what good alignment looks like)."""
    x = np.linspace(-np.pi, np.pi, size)
    X, Y = np.meshgrid(x, x)
    return (0.5 + 0.4 * np.cos(fx * X + fy * Y)).astype(np.float64)


def _uniform(size=256):
    return np.full((size, size), 0.5)


# ── sideband metric ──────────────────────────────────────────────────────────

def test_sideband_high_for_fringes_low_for_uniform():
    fringey = calculate_sideband_energy(_fringes())
    flat    = calculate_sideband_energy(_uniform())
    # The whole point of the metric: clear fringes score far above a flat field,
    # so the optimizer can climb toward good polarization.
    assert fringey > flat
    assert fringey > 10 * flat


def _dual_fringes(size=256, a1=0.4, a2=0.4):
    """Two off-axis carriers on the two diagonals — a dual-polarization
    hologram. a1/a2 set each polarization's fringe contrast."""
    x = np.linspace(-np.pi, np.pi, size)
    X, Y = np.meshgrid(x, x)
    return (0.5 + a1 * np.cos(10 * X + 6 * Y)        # carrier 1 -> UL/LR
                + a2 * np.cos(-7 * X + 8 * Y)).astype(float)   # carrier 2 -> UR/LL


def test_balance_metric_rewards_both_axes():
    bw, ba, bb = calculate_sideband_balance(_dual_fringes(a1=0.4, a2=0.4))   # balanced
    lw, la, lb = calculate_sideband_balance(_dual_fringes(a1=0.4, a2=0.03))  # one axis starved
    assert bw == min(ba, bb) and lw == min(la, lb)     # returns the weaker axis
    assert bw > lw                                      # balancing lifts the weak axis
    # The point of the metric: a starved axis shows a large strong/weak imbalance,
    # a balanced one stays close to even.
    assert max(la, lb) / min(la, lb) > 2 > max(ba, bb) / min(ba, bb)


def test_sideband_handles_nonsquare_frame():
    # The Bobcat 320 is 320x256; the metric center-crops internally. Just make
    # sure a non-square frame doesn't raise.
    rect = _fringes()[:200, :256]
    val = calculate_sideband_energy(rect)
    assert np.isfinite(val)


# ── saturation detection ───────────────────────────────────────────────────────

def test_clean_frame_not_saturated():
    frame = (_fringes() * 30000).astype(np.uint16)   # well under the 65535 ceiling
    sat = check_saturation(frame, sat_level=65535)
    assert sat["saturated"] is False
    assert sat["n_saturated"] == 0


def test_clipped_frame_is_saturated():
    frame = (_fringes() * 30000).astype(np.uint16)
    frame[:50, :50] = 65535                            # ~4% of pixels clipped
    sat = check_saturation(frame, sat_level=65535, sat_fraction_max=0.001)
    assert sat["saturated"] is True
    assert sat["n_saturated"] == 50 * 50
    assert sat["max_value"] == 65535


def test_saturation_fraction_threshold():
    frame = np.zeros((256, 256), np.uint16)
    frame[0, 0] = 65535                                # a single hot pixel
    # one pixel out of 65536 is below the default 0.1% tolerance -> not flagged
    assert check_saturation(frame, sat_fraction_max=0.001)["saturated"] is False
