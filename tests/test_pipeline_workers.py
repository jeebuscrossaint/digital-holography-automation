# -*- coding: utf-8 -*-
"""process_records(workers=N) must return exactly what the serial loop does.

Frames are independent, so the pool only changes where each one runs; any
difference in the rows means state leaked between frames or the results were
reassembled in the wrong order. The processor's search grid is shrunk so this
spawns real worker processes but still finishes in seconds.
"""

import numpy as np
import pytest

from conftest import FIXTURES


@pytest.fixture
def records(tmp_path):
    frame = np.load(FIXTURES / "sample_hologram.npy")
    recs = []
    for leg, wl in ((1, 1525.0), (2, 1525.0), (1, 1550.0), (2, 1550.0)):
        path = tmp_path / f"leg{leg:02d}-wavelength{int(wl)}.npy"
        np.save(path, frame)
        recs.append({"path": path, "label": path.stem, "leg": leg, "wl": wl})
    return recs


def _small_processor():
    from holo.data_processing import HolographyDataProcessor
    proc = HolographyDataProcessor()
    proc._lp_cuts = [22]
    proc._fovs = [30e-6, 40e-6]
    proc._phases = np.array([0.0])
    return proc


def test_worker_pool_matches_serial(records):
    from holo import pipeline
    rows = {}
    for workers in (1, 2):
        rows[workers] = pipeline.process_records(
            _small_processor(), records, config={}, use_multiport=False,
            save=False, workers=workers)
    assert len(rows[1]) == len(records)
    assert rows[2] == rows[1]
    assert [r["source"] for r in rows[2]] == [r["label"] for r in records]
