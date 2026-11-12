"""Keep display work independent of full-recording reads and repeated rendering."""

from pathlib import Path
from types import SimpleNamespace

import matplotlib

matplotlib.use("Agg")
import numpy as np
import polars as pl
import pytest

from fall_detection.analysis import sequence_reporting as reporting
from fall_detection.analysis.sequence_cache import save_segment


@pytest.fixture
def workflow(tmp_path):
    n = 257
    amplitude = np.full((n, 4, 245), 20.0, dtype=np.float64)
    amplitude[1] = np.nan
    amplitude[17, 0, 152] = np.nan
    path = tmp_path / "representative"
    save_segment(
        path,
        {
            "amplitude": amplitude,
            "filtered_amplitude": amplitude,
            "squared_difference": np.zeros_like(amplitude),
            "valid": np.isfinite(amplitude),
            "hampel_replaced": np.zeros_like(amplitude, dtype=bool),
            "time_ns": np.arange(n, dtype=np.int64) * 10_416_667,
            "subcarriers": np.arange(-122, 123),
            "unrelated": np.ones(1),
        },
    )
    np.save(tmp_path / "signal.npy", amplitude)
    frame = pl.DataFrame(
        {
            "receiver": ["rx-1", "rx-2", "rx-3", "rx-4"],
            "replaced": [0] * 4,
            "valid": [100] * 4,
        }
    )
    return SimpleNamespace(
        name="test",
        output=tmp_path,
        segments=pl.DataFrame(
            [
                {
                    "path": str(path),
                    "segment_id": "s",
                    "samples": n,
                    "activity_label": "non_fall",
                    "attempt_key": "attempt",
                }
            ]
        ),
        index=pl.DataFrame(
            [
                {
                    "duration": d,
                    "segment_id": "s",
                    "signal": "signal.npy",
                    "start": 0,
                    "stop": 192,
                    "start_ns": i * 1_000_000,
                    "coverage": 0.8,
                    "target": 0,
                }
                for d in (2, 4, 6)
                for i in range(100)
            ]
        ),
        signals=pl.DataFrame([{"segment_id": "s", "samples": n, "bytes": 1000}]),
        timings={"load": 0.1},
        hampel=frame,
        alignment=pl.DataFrame({"gap_rounds": [[1]], "gap_counts": [[10]]}),
    )


def test_availability_bins_include_short_gaps(workflow):
    values = reporting.preview_array(workflow.segments["path"][0], "availability", 16)
    assert values.shape == (16, 4)
    assert (values[0] < 1).all() and (values[0] > 0).all()


def test_preview_preserves_missing_values_and_invalidates_changed_array(workflow):
    path = workflow.segments["path"][0]
    preview = reporting.preview_array(path, "amplitude", 16)
    assert preview.shape == (16, 4, 245)
    assert np.isnan(preview[1, 0, 152])
    save_segment(Path(path), {"amplitude": np.full((257, 4, 245), 3.0)})
    np.testing.assert_array_equal(reporting.preview_array(path, "amplitude", 16), 3.0)


def test_preview_reuses_bounded_sample(workflow, monkeypatch):
    path = workflow.segments["path"][0]
    first = reporting.preview_array(path, "amplitude", 16)
    monkeypatch.setattr(
        reporting, "read_segment", lambda *a: pytest.fail("reloaded cached preview")
    )
    assert reporting.preview_array(path, "amplitude", 16) is first
