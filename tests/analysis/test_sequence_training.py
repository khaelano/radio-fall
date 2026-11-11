"""Leakage, input semantics, and model/checkpoint lifecycle checks."""

import numpy as np
import polars as pl
import pytest

from fall_detection.analysis.sequence_training_data import (
    Normalizer,
    SegmentStore,
    SequenceDataset,
    ShardStore,
    fit_normalizer,
    prefetched_batches,
    split_sequence_attempts,
)


def test_split_keeps_attempts_and_durations_together():
    rows = [
        {
            "group": f"{dataset}-{target}-{attempt}",
            "dataset": dataset,
            "activity_label": f"activity-{target}",
            "target": target,
            "duration": duration,
        }
        for dataset in ("a", "b", "continuous_non_fall")
        for target in ((0,) if dataset == "continuous_non_fall" else (0, 1))
        for attempt in range(20)
        for duration in (2, 4, 6)
        for _ in range(2)
    ]
    index = pl.DataFrame(rows)
    split = split_sequence_attempts(index)
    assert split.equals(split_sequence_attempts(index))
    assert split.group_by("group").agg(pl.col("split").n_unique())["split"].max() == 1
    assert split.group_by("split").len().sort("split")["len"].to_list() == [
        120,
        360,
        120,
    ]


def test_streaming_normalization_masks_labels_and_training_isolation(tmp_path):
    path = tmp_path / "shard.npz"
    raw = np.full((3, 192, 1, 2), 3.0)
    raw[0, :96, 0, 0] = 0
    raw[0, 0, 0, 1] = np.nan
    raw[1] = 1e20  # Held-out signals must not affect fitted statistics.
    raw[2] = 99
    valid = np.ones_like(raw, dtype=bool)
    valid[2] = False
    np.savez_compressed(
        path,
        squared_difference=raw,
        difference_valid=valid,
        target=np.array([1, 0, 0]),
        receivers=["rx-1"],
        subcarriers=[-1, 1],
    )
    index = pl.DataFrame(
        [
            {
                "path": str(path),
                "shard_row": i,
                "target": target,
                "duration": 2,
                "window_id": i,
                "split": split,
                "dataset": "synthetic",
            }
            for i, target, split in ((0, 1, "train"), (1, 0, "test"), (2, 0, "train"))
        ]
    )
    store = ShardStore(max_bytes=1)  # Exercise the uncached oversized-shard path.
    normalizer = fit_normalizer(index, store)
    np.testing.assert_allclose(normalizer.mean, [np.log(4) / 2, np.log(4)], rtol=1e-6)
    np.testing.assert_array_equal(normalizer.count, [192, 191])
    normalizer.save(tmp_path / "normalizer.npz")
    normalizer = Normalizer.load(tmp_path / "normalizer.npz")
    dataset = SequenceDataset(index, normalizer, store)
    batches = list(dataset.batches(2, seed=42))
    prefetched = list(prefetched_batches(dataset, 2, seed=42))
    for (expected, metadata), (actual, actual_metadata) in zip(batches, prefetched):
        np.testing.assert_array_equal(actual, expected)
        assert actual_metadata == metadata
    assert sum(len(rows) for _, rows in batches) == 3
    for values, rows in batches:
        assert values.shape[1:] == (192, 4)
        assert np.isfinite(values).all()
        for x, row in zip(values, rows):
            if row["window_id"] == 2:
                np.testing.assert_array_equal(x, 0)
            if row["window_id"] == 0:
                assert x[0, 1] == x[0, 3] == 0
    assert store.bytes == 0
    wrong = index.with_columns(pl.lit(0).alias("target"))
    with pytest.raises(ValueError, match="targets differ"):
        list(SequenceDataset(wrong, normalizer, store).batches(2))


def test_segment_slices_keep_nan_mask_and_deterministic_batches(tmp_path):
    signal = np.full((288, 4, 245), 3, dtype=np.float32)
    signal[0, 0, 0] = np.nan
    path = tmp_path / "segment.npy"
    np.save(path, signal)
    frame = pl.DataFrame(
        [
            {
                "path": str(path),
                "start": start,
                "stop": start + 192,
                "duration": 2,
                "target": 0,
                "split": "train",
                "window_id": i,
            }
            for i, start in enumerate((0, 96))
        ]
    )
    store = SegmentStore()
    normalizer = fit_normalizer(frame, store)
    np.testing.assert_array_equal(normalizer.count[:1], [383])
    dataset = SequenceDataset(frame, normalizer, store)
    first = list(dataset.batches(2, seed=7))
    again = list(dataset.batches(2, seed=7))
    np.testing.assert_array_equal(first[0][0], again[0][0])
    assert first[0][1] == again[0][1]
    assert first[0][0].shape == (2, 192, 1960)
    assert np.isfinite(first[0][0]).all()


def test_full_rate_batch_includes_packet_presence(tmp_path):
    path = tmp_path / "segment.npy"
    signal = np.ones((240, 4, 245), dtype=np.float32)
    signal[4, 0] = np.nan
    np.save(path, signal)
    presence = np.ones((240, 4), dtype=bool)
    presence[4, 0] = False
    presence[5, 1] = False
    np.save(tmp_path / "segment.presence.npy", presence)
    frame = pl.DataFrame(
        [
            {
                "path": str(path),
                "start": 0,
                "stop": 240,
                "duration": 2,
                "rate_hz": 120,
                "target": 0,
                "split": "train",
                "window_id": 0,
            }
        ]
    )
    store = SegmentStore()
    dataset = SequenceDataset(frame, fit_normalizer(frame, store), store)
    values, _ = next(dataset.batches(1))
    assert values.shape == (1, 240, 1964)
    np.testing.assert_array_equal(values[0, :, -4:], presence)
    assert not values[0, 4, 980:1225].any()
