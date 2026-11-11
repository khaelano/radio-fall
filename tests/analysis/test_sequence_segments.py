"""The direct v2 export and memory-mapped loader share one signal contract."""

import json

import numpy as np
import polars as pl

from fall_detection.analysis.sequence_cache import save_segment
from fall_detection.analysis.sequence_segments import export_cached_segments
from fall_detection.analysis.sequence_training_data import SegmentStore, _selected


def test_direct_export_preserves_values_and_invalidity(tmp_path):
    source = tmp_path / "stage"
    destination = tmp_path / "v2"
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
    assert manifest["schema"] == "amplitude_sequence_v2"
    row = pl.read_parquet(destination / "window_index.parquet").row(0, named=True)
    values, mask = _selected(SegmentStore(), str(destination / row["signal"]), [row])
    assert values.shape == mask.shape == (1, 192, 980)
    assert not mask[0, 0, 0] and values[0, 0, 0] == 0
    assert values[0, 1, 0] == np.float32(np.log1p(3.0))
