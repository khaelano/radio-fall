"""Exercise data preparation and the notebook's visible training cells."""

import json

import numpy as np
import polars as pl

from fall_detection.analysis.amplitude_pipeline import save_recording
from fall_detection.analysis.window_data import (
    index_windows,
    pooled_input,
    save_manifest,
    split_attempts,
)


def test_pooling_ignores_missing_and_exposes_coverage():
    values = np.array([[1.0], [99.0], [3.0], [5.0]], dtype=np.float32)
    mask = np.array([[1], [0], [1], [1]], dtype=bool)
    np.testing.assert_array_equal(
        pooled_input(values, mask, 2), [[1.0, 0.5], [4.0, 1.0]]
    )


def test_grouped_synthetic_windows_keep_attempts_together(tmp_path):
    root = tmp_path / "windows"
    for duration in (2, 4, 6):
        for attempt in range(10):
            for receiver in ("rx-1", "rx-2"):
                path = root / f"{duration}s" / f"trial{attempt}" / f"{receiver}.npz"
                data = (
                    np.random.default_rng(attempt)
                    .normal(size=(3, duration * 80, 4))
                    .astype("f4")
                )
                save_recording(
                    path,
                    {
                        "amplitude": data,
                        "valid": np.ones_like(data, dtype=bool),
                        "label": np.array(["preparation", "action", "resting"]),
                        "provenance_json": np.asarray(
                            json.dumps(
                                {
                                    "session_id": "session",
                                    "attempt_key": f"trial{attempt}",
                                    "receiver_id": receiver,
                                }
                            )
                        ),
                    },
                )
    index = split_attempts(index_windows(root), 42)
    assert (
        index.group_by("group").agg(pl.col("split").n_unique().alias("n"))["n"].max()
        == 1
    )
    save_manifest(index, tmp_path / "results", {"split_seed": 42})
