# -*- coding: utf-8 -*-
"""Input discovery for the headless CLI (process.py).

The pipeline is only as good as what it is handed, and a whole sweep can be
silently thrown away here without anything erroring — so the leg x wavelength
grid is pinned.
"""

import numpy as np
import pytest


@pytest.fixture
def sweep(tmp_path):
    """A 3-leg x 4-wavelength sweep in the collector's filename layout."""
    for leg in (1, 2, 3):
        for wl in (1525, 1550, 1560, 1575):
            np.save(tmp_path / f"leg{leg:02d}-wavelength{wl:04d}.npy",
                    np.zeros((8, 8)))
    return tmp_path


def test_discovers_every_leg_wavelength_pair(sweep):
    # Regression: discovery used to key on the leg alone, so a sweep collapsed
    # to one frame per leg — 3 of 12 here — with no error to show for it.
    from process import discover
    records = discover(sweep, default_wl=1550)
    assert len(records) == 12
    assert {(r["leg"], int(r["wl"])) for r in records} == {
        (leg, wl) for leg in (1, 2, 3) for wl in (1525, 1550, 1560, 1575)}


def test_prefers_array_over_image_for_the_same_frame(tmp_path):
    from PIL import Image
    from process import discover
    np.save(tmp_path / "leg01-wavelength1550.npy", np.zeros((8, 8)))
    Image.fromarray(np.zeros((8, 8), np.uint16)).save(
        tmp_path / "leg01-wavelength1550.png")
    records = discover(tmp_path, default_wl=1550)
    # One frame, and the 16-bit-safe array wins over the image.
    assert len(records) == 1
    assert records[0]["src"].suffix == ".npy"


def test_sidecar_wavelength_overrides_the_filename(tmp_path):
    from process import discover
    np.save(tmp_path / "leg01-wavelength1550.npy", np.zeros((8, 8)))
    (tmp_path / "leg01-wavelength1550.yaml").write_text("wavelength_nm: 1552.5\n")
    records = discover(tmp_path, default_wl=1550)
    assert records[0]["wl"] == pytest.approx(1552.5)


def test_frames_without_a_leg_number_are_enumerated(tmp_path):
    from process import discover
    for name in ("alpha", "beta", "gamma"):
        np.save(tmp_path / f"{name}.npy", np.zeros((8, 8)))
    records = discover(tmp_path, default_wl=1550)
    assert len(records) == 3
    assert sorted(r["leg"] for r in records) == [1, 2, 3]
