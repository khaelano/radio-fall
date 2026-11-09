import json
import time

import numpy as np
import pytest

from fall_detection import _radio_native as core


@pytest.mark.parametrize("full", [False, True])
def test_native_window_preserves_physical_tones_masks_and_half_open_boundaries(
    native_record, full
):
    first, old = native_record(1, weak=True, full=full)
    second, _ = native_record(2, full=full)
    bad, _ = native_record(3, bad=True, full=full)
    start = 10_000_000_000
    rows = [
        (record, rx, t)
        for rx in range(4)
        for record, t in [
            (second, start - 100_000_000),
            (first, start),
            (second, start + 40_000_000),
            (bad, start + 80_000_000),
            (second, start + 4_000_000_000),
        ]
    ]
    native = core.CnnPreprocessor([1.0] * 968, [2.0] * 968)
    try:
        window = native.build(rows, start)
        raw = np.frombuffer(window.raw_bytes(), dtype="=f4").reshape(4, 100, 242)
        tensor = np.frombuffer(window.tensor_bytes(), dtype="=f4").reshape(8, 100, 242)
        block = old.channel_estimate_block
        order = np.argsort(block.subcarrier_indices)
        indices = np.asarray(block.subcarrier_indices)[order]
        keep = (np.abs(indices) <= 122) & (np.abs(indices) > 1)
        valid = np.isfinite(np.array(block.raw_phases)[order][keep]) & np.isfinite(
            np.array(block.calibrated_phases)[order][keep]
        )
        reference = np.where(
            valid, np.log1p(np.array(block.amplitudes)[order][keep]), np.nan
        ).astype("float32")
        np.testing.assert_allclose(raw[0, 0], reference, atol=1e-6, equal_nan=True)
        assert np.isnan(raw[:, 2:]).all()
        np.testing.assert_allclose(
            tensor[:4], np.where(np.isfinite(raw), (raw - 1) / 2, 0), atol=0
        )
        np.testing.assert_array_equal(tensor[4:], np.isfinite(raw))
        meta = json.loads(window.metadata_json())
        assert meta["packets"] == [3] * 4
        assert not meta["valid"]
    finally:
        native.close()


def test_simd_and_scalar_inputs_are_identical_after_reordering_and_duplicates(
    native_record,
):
    rows = []
    start = 10_000_000_000
    for i in range(110):
        record, _ = native_record(i + 1, weak=i % 3 == 0, bad=i % 17 == 0)
        rows.extend(
            (record, rx, start - 100_000_000 + i * 40_000_000) for rx in range(4)
        )
    processors = [
        core.CnnPreprocessor([1.0] * 968, [2.0] * 968, kernel=kernel)
        for kernel in ["scalar", "auto"]
    ]
    try:
        scalar = processors[0].build(rows, start)
        vector = processors[1].build(list(reversed(rows)) + rows[:4], start)
        assert scalar.tensor_bytes() == vector.tensor_bytes()
        for key in ["phase_change_coverage", "amplitude_coverage", "packets", "valid"]:
            assert (
                json.loads(scalar.metadata_json())[key]
                == json.loads(vector.metadata_json())[key]
            )
    finally:
        for processor in processors:
            processor.close()


def test_native_configuration_is_bounded_and_rejects_invalid_normalization():
    for kwargs in [
        dict(workers=0),
        dict(capacity=0),
        dict(hop_ms=1),
        dict(grace_ms=2001),
        dict(kernel="gpu"),
    ]:
        with pytest.raises(ValueError):
            core.CnnPreprocessor([0.0] * 968, [1.0] * 968, **kwargs)
    with pytest.raises(ValueError):
        core.CnnPreprocessor([float("nan")] * 968, [1.0] * 968)


def test_native_reset_invalidates_generation_and_closed_input_is_rejected(
    native_record,
):
    processor = core.CnnPreprocessor([0.0] * 968, [1.0] * 968)
    record, _ = native_record()
    try:
        before = json.loads(processor.stats_json())["generation"]
        processor.reset()
        assert json.loads(processor.stats_json())["generation"] == before + 1
        assert processor.poll() is None
        with pytest.raises(ValueError):
            processor.submit(record, 4, time.monotonic_ns(), 1, 2, 3)
    finally:
        processor.close()
    assert not processor.submit(record, 0, time.monotonic_ns(), 1, 2, 3)


def test_native_receiver_boot_change_invalidates_all_receiver_windows(native_record):
    processor = core.CnnPreprocessor([0.0] * 968, [1.0] * 968)
    record, _ = native_record()
    try:
        processor.submit(record, 0, time.monotonic_ns(), 1, 2, 3)
        processor.submit(record, 0, time.monotonic_ns(), 1, 2, 4)
        deadline = time.monotonic() + 5
        while (
            json.loads(processor.stats_json())["generation"] == 1
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert json.loads(processor.stats_json())["generation"] == 2
        assert processor.poll() is None
    finally:
        processor.close()
