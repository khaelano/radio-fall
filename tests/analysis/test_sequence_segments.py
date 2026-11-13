"""Signal publication preserves values, validity, and an existing destination."""

import json

import numpy as np
import polars as pl
import pytest

from fall_detection.analysis.preprocessing.sequence_segments import (
    publish_export,
    write_signal,
)
from fall_detection.analysis.training.sequence_training_data import (
    SegmentStore,
    _selected,
)


def test_publish_preserves_values_and_invalidity(tmp_path):
    signal = np.full((192, 4, 245), np.log1p(3.0), dtype=np.float32)
    signal[0, 0, 0] = np.nan
    row = dict(
        segment_id="one",
        **write_signal(tmp_path / "signals/one.npy", signal),
        subcarriers=list(range(-122, 123)),
    )
    index = pl.DataFrame(
        [
            {
                "segment_id": "one",
                "signal": "signals/one.npy",
                "duration": 2,
                "start": 0,
                "stop": 192,
                "target": 1,
            }
        ]
    )
    segments = pl.DataFrame([{"segment_id": "one", "samples": 192}])
    publish_export(
        tmp_path,
        index,
        segments,
        [row],
        seconds=0,
        source_metadata={"source_fingerprint": "fixture"},
        parameters={"target_hz": 96, "label_policy": "test labels"},
    )
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["schema"] == "amplitude_sequence"
    assert manifest["labels"]["rule"] == "test labels"
    row = index.row(0, named=True)
    values, mask = _selected(SegmentStore(), str(tmp_path / row["signal"]), [row])
    assert values.shape == mask.shape == (1, 192, 980)
    assert not mask[0, 0, 0] and values[0, 0, 0] == 0
    assert values[0, 1, 0] == np.float32(np.log1p(3.0))
    # Publishing identical tables must not invalidate preprocessing checkpoints.
    stamp = (tmp_path / "segments.parquet").stat().st_mtime_ns
    publish_export(
        tmp_path,
        index,
        segments,
        [
            dict(
                segment_id="one",
                **write_signal(tmp_path / "signals/one.npy", signal),
                subcarriers=list(range(-122, 123)),
            )
        ],
        seconds=0,
        parameters={"target_hz": 96},
    )
    assert (tmp_path / "segments.parquet").stat().st_mtime_ns == stamp


def test_failed_signal_write_preserves_existing_file(tmp_path, monkeypatch):
    path = tmp_path / "signals/one.npy"
    signal = np.ones((4, 4, 245), dtype=np.float32)
    write_signal(path, signal)
    original = path.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("synthetic write failure")

    monkeypatch.setattr(np, "save", fail)
    with pytest.raises(OSError, match="synthetic write failure"):
        write_signal(path, signal * 2)
    assert path.read_bytes() == original
    assert list(path.parent.iterdir()) == [path]


def test_export_code_hashes_cover_every_format_module():
    from fall_detection.analysis.preprocessing.sequence_segments import (
        export_code_hashes,
    )

    hashes = export_code_hashes()

    assert set(hashes) == {
        "sequence_segments.py",
        "sequence_preprocessing.py",
        "_io.py",
        "_cache_keys.py",
    }
    assert all(len(digest) == 64 for digest in hashes.values())
