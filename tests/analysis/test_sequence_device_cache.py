"""Device cache input parity, compact storage, and bounded fallback."""

import numpy as np
import polars as pl
import pytest

torch = pytest.importorskip("torch")

from fall_detection.analysis.sequence_device_cache import (
    prepare_device_dataset,
    training_batches,
)
from fall_detection.analysis.sequence_training_data import (
    SegmentStore,
    SequenceDataset,
    fit_normalizer,
)


@pytest.mark.parametrize("device_name", ["cpu", "cuda"])
@pytest.mark.parametrize("rate", [96, 120])
def test_device_cache_matches_streaming_and_stores_segments_once(
    tmp_path, monkeypatch, device_name, rate
):
    if device_name == "cuda" and not torch.cuda.is_available():
        pytest.skip("CUDA unavailable")
    rng = np.random.default_rng(17)
    rows = []
    for number in range(2):
        path = tmp_path / f"segment-{number}.npy"
        signal = rng.normal(size=(rate + 40, 4, 245)).astype(np.float32)
        signal[::3, 1, 20] = np.nan
        np.save(path, signal)
        np.save(path.with_suffix(".presence.npy"), rng.random((rate + 40, 4)) > 0.1)
        rows.extend(
            {
                "path": str(path),
                "start": i,
                "stop": i + rate,
                "duration": 1,
                "rate_hz": rate,
                "target": i % 2,
                "window_id": number * 25 + i,
                "split": "train",
            }
            for i in range(10, 35)
        )
    frame = pl.DataFrame(rows)
    store = SegmentStore()
    dataset = SequenceDataset(frame, fit_normalizer(frame, store), store)
    expected = {
        (size, seed): list(dataset.batches(size, seed))
        for size in (7, 32)
        for seed in (None, 42, 43)
    }
    device = torch.device(device_name)
    assert prepare_device_dataset(dataset, device, 0) is None
    original_empty = torch.empty
    allocations = 0

    def allocation_failure(*args, **kwargs):
        nonlocal allocations
        allocations += 1
        if allocations == 2:
            raise torch.cuda.OutOfMemoryError("simulated concurrent allocation")
        return original_empty(*args, **kwargs)

    with monkeypatch.context() as allocation_patch:
        allocation_patch.setattr(torch, "empty", allocation_failure)
        assert prepare_device_dataset(dataset, device, 128 * 2**20) is None
    cache = prepare_device_dataset(dataset, device, 128 * 2**20)
    assert cache is not None
    assert cache.device_bytes == 2 * (rate + 24) * (980 * 5 + (4 if rate == 120 else 0))
    assert cache.device_bytes < sum(x.nbytes for x, _ in expected[7, None])
    assert cache.valid.dtype == torch.bool
    assert cache.frame.equals(frame)

    def unexpected_read(*args, **kwargs):
        raise AssertionError("Device cache must not reread or normalize signals")

    monkeypatch.setattr(store, "read", unexpected_read)
    monkeypatch.setattr(dataset.normalizer, "transform", unexpected_read)
    for (size, seed), batches in expected.items():
        actual = list(training_batches(cache, size, seed))
        assert len(actual) == len(batches)
        for (values, metadata), (cached, cached_metadata) in zip(batches, actual):
            assert cached.device.type == device_name
            np.testing.assert_array_equal(cached.cpu().numpy(), values)
            assert cached_metadata == metadata


def test_device_cache_rejects_bad_presence_and_window_bounds(tmp_path):
    path = tmp_path / "segment.npy"
    np.save(path, np.ones((120, 4, 245), dtype=np.float32))
    np.save(path.with_suffix(".presence.npy"), np.ones((119, 4), dtype=bool))
    frame = pl.DataFrame(
        [
            {
                "path": str(path),
                "start": 0,
                "stop": 120,
                "duration": 1,
                "rate_hz": 120,
                "split": "train",
            }
        ]
    )
    store = SegmentStore()
    dataset = SequenceDataset(frame, fit_normalizer(frame, store), store)
    with pytest.raises(ValueError, match="presence mask"):
        prepare_device_dataset(dataset, torch.device("cpu"), 2**20)
    dataset.parts[0][1][0]["stop"] = 119
    with pytest.raises(ValueError, match="Window bounds"):
        prepare_device_dataset(dataset, torch.device("cpu"), 2**20)
