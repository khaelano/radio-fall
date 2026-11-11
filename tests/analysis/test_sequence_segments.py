"""The direct export and memory-mapped loader share one signal contract."""

import json

import numpy as np
import polars as pl

from fall_detection.analysis.sequence_cache import save_segment
from fall_detection.analysis.sequence_segments import export_cached_segments
from fall_detection.analysis.sequence_training_data import SegmentStore, _selected


def test_direct_export_preserves_values_and_invalidity(tmp_path):
    source = tmp_path / "stage"
    destination = tmp_path / "96hz"
    path = source / "segments" / "one"
    raw = np.full((192, 4, 245), 3.0)
    raw[0, 0, 0] = np.nan
    valid = np.isfinite(raw)
    save_segment(
        path,
        dict(
            squared_difference=raw,
            difference_valid=valid,
            receivers=np.asarray([f"rx-{i}" for i in range(1, 5)]),
            subcarriers=np.arange(-122, 123),
        ),
    )
    index = pl.DataFrame(
        [
            dict(
                segment_id="one",
                duration=2,
                start=0,
                stop=192,
                target=1,
                group="attempt",
            )
        ]
    )
    segments = pl.DataFrame([dict(segment_id="one", path=str(path), samples=192)])
    export_cached_segments(
        source,
        destination,
        index,
        segments,
        source_metadata={"source_fingerprint": "fixture"},
        parameters={"target_hz": 96},
    )
    manifest = json.loads((destination / "manifest.json").read_text())
    assert manifest["schema"] == "amplitude_sequence"
    row = pl.read_parquet(destination / "window_index.parquet").row(0, named=True)
    values, mask = _selected(SegmentStore(), str(destination / row["signal"]), [row])
    assert values.shape == mask.shape == (1, 192, 980)
    assert not mask[0, 0, 0] and values[0, 0, 0] == 0
    assert values[0, 1, 0] == np.float32(np.log1p(3.0))


def test_full_rate_export_keeps_packet_presence(tmp_path):
    path = tmp_path / "stage" / "one"
    capture = np.full((240, 4), 100, dtype=np.int64)
    capture[10, 2] = -1
    raw = np.ones((240, 4, 245))
    raw[10, 2] = np.nan
    save_segment(
        path,
        {
            "squared_difference": raw,
            "difference_valid": np.isfinite(raw),
            "capture_time_ns": capture,
            "receivers": np.asarray([f"rx-{i}" for i in range(1, 5)]),
            "subcarriers": np.arange(-122, 123),
        },
    )
    index = pl.DataFrame(
        [
            {
                "segment_id": "one",
                "duration": 2,
                "start": 0,
                "stop": 240,
                "target": 1,
                "group": "attempt",
            }
        ]
    )
    segments = pl.DataFrame([{"segment_id": "one", "path": str(path), "samples": 240}])
    destination = tmp_path / "120hz"
    export_cached_segments(
        tmp_path / "stage",
        destination,
        index,
        segments,
        source_metadata={"source_fingerprint": "fixture"},
        parameters={"target_hz": 120},
    )
    ledger = pl.read_parquet(destination / "signals.parquet").row(0, named=True)
    np.testing.assert_array_equal(
        np.load(destination / ledger["presence"]), capture >= 0
    )
    assert not np.isfinite(np.load(destination / ledger["signal"])[10, 2]).any()
