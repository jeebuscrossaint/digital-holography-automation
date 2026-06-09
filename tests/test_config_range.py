# -*- coding: utf-8 -*-
"""The wavelength/leg sweep can be written as a {start, stop, step} range
instead of listing every value; the loader expands it to an inclusive list."""


def test_wavelength_range_expands():
    from gui.app import HolographyApp
    f = HolographyApp._expand_range
    assert f({"start": 1525, "stop": 1575, "step": 5}) == \
        [1525, 1530, 1535, 1540, 1545, 1550, 1555, 1560, 1565, 1570, 1575]
    assert f({"start": 1, "stop": 3, "step": 1}) == [1, 2, 3]
    assert f({"start": 1550, "stop": 1550, "step": 5}) == [1550]   # single point
    assert f({"start": 3, "stop": 1, "step": 1}) == [3, 2, 1]       # descending
    assert f({"start": 1525, "stop": 1526, "step": 0.5}) == [1525, 1525.5, 1526]


def test_capture_filename_handles_fractional_wavelengths():
    from gui.experiment import format_capture_name
    fmt = "leg{leg:02d}-wavelength{wavelength:04d}.npy"
    # whole numbers unchanged (backward compatible)
    assert format_capture_name(fmt, 1, 1525) == "leg01-wavelength1525.npy"
    assert format_capture_name(fmt, 1, 1550.0) == "leg01-wavelength1550.npy"
    # fractional wavelength: dot-free tag, doesn't crash the integer format code
    assert format_capture_name(fmt, 1, 1525.1) == "leg01-wavelength1525p1.npy"
    assert format_capture_name(fmt, 12, 1530.25) == "leg12-wavelength1530p25.npy"
