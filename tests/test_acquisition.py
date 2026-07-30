# -*- coding: utf-8 -*-
"""Repeated exposures must land in separate repNN folders.

``discovery.discover`` keeps exactly one file per (leg, wavelength), so three
exposures written side by side in one folder would leave two silently
unprocessed. One folder per repeat keeps each a complete, processable sweep.
"""

import numpy as np

from holo import acquisition, discovery


class _Cam:
    """Fake camera: a different frame each grab, so repeats are distinguishable."""

    def __init__(self):
        self.n = 0

    def getFrame(self):
        self.n += 1
        y, x = np.mgrid[0:64, 0:64]
        return (8000 + 3000 * np.cos(0.4 * x) + self.n).astype(np.uint16)


class _Laser:
    def __init__(self):
        self.wl = 1550.0
        self.last_error = None

    def changeWavelength(self, nm):
        self.wl = float(nm)

    def checkWavelength(self, s=''):
        return self.wl

    def outputState(self, tf):
        pass

    def isOutputOn(self):
        return "1"


def test_repeats_go_in_separate_folders(tmp_path):
    rows = acquisition.sweep(_Cam(), _Laser(), [1530, 1531], tmp_path,
                            leg=4, repeats=3, dwell=0, log=lambda *a: None)

    assert len(rows) == 6
    assert sorted(p.name for p in tmp_path.iterdir()) == ["rep01", "rep02", "rep03"]

    # every repeat is a whole sweep discovery can read, with nothing deduped away
    for rep in ("rep01", "rep02", "rep03"):
        found = discovery.discover(tmp_path / rep)
        assert [(r["leg"], r["wl"]) for r in found] == [(4, 1530.0), (4, 1531.0)]

    # ...and they are genuinely separate exposures, not one frame saved thrice
    a = np.load(tmp_path / "rep01" / "leg04-wavelength1530.npy")
    b = np.load(tmp_path / "rep02" / "leg04-wavelength1530.npy")
    assert not np.array_equal(a, b)


def test_single_exposure_keeps_the_flat_layout(tmp_path):
    """repeats=1 writes straight into the output folder — the layout the GUI
    has always produced, so existing datasets and scripts still line up."""
    acquisition.sweep(_Cam(), _Laser(), [1530], tmp_path, repeats=1, dwell=0,
                      log=lambda *a: None)
    assert (tmp_path / "leg01-wavelength1530.npy").exists()
    assert not (tmp_path / "rep01").exists()


def test_sidecar_records_commanded_and_measured_wavelength(tmp_path):
    """The 8168E queues errors instead of raising, so a rejected :WAVE leaves it
    at the old wavelength. Recording both is what makes that detectable later."""
    import yaml

    class Stuck(_Laser):
        def changeWavelength(self, nm):
            pass                      # accepts the command, never tunes

    acquisition.sweep(_Cam(), Stuck(), [1530], tmp_path, dwell=0,
                      log=lambda *a: None)
    meta = yaml.safe_load((tmp_path / "leg01-wavelength1530.yaml").read_text())
    assert meta["wavelength_commanded_nm"] == 1530.0
    assert meta["wavelength_measured_nm"] == 1550.0


def test_plan_matches_what_a_sweep_writes(tmp_path):
    planned = acquisition.plan([1530, 1531], tmp_path, leg=2, repeats=2)
    acquisition.sweep(_Cam(), _Laser(), [1530, 1531], tmp_path, leg=2,
                      repeats=2, dwell=0, log=lambda *a: None)
    assert sorted(planned) == sorted(tmp_path.rglob("*.npy"))
