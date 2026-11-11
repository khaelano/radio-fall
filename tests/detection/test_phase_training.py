"""Native phase regression coverage independent of retired training notebooks."""

import numpy as np
import pytest


def reference_phase_windows(rows: list, starts: list[int]) -> np.ndarray:
    """Independently compute lagged phase/bin means with integer capture times."""
    result = [[] for _ in starts]
    for rx in range(4):
        unique = {(t, r.sequence): r for r, receiver, t in rows if receiver == rx}
        times, phases = [], []
        for (capture, _), record in sorted(unique.items()):
            encoded = record.wire
            phase = record.phase_bytes()
            if encoded[37:40] != bytes([4, 0, 0]) or phase is None:
                continue
            tones, _, raw, calibrated = phase
            order = np.argsort(tones)
            tones = np.asarray(tones)[order]
            keep = (np.abs(tones) > 1) & (np.abs(tones) <= 122)
            values = np.frombuffer(calibrated, dtype="=f8")[order][keep].copy()
            valid = np.isfinite(np.frombuffer(raw, dtype="=f8")[order][keep])
            values[~valid] = np.nan
            if encoded[50] != 0:
                values[:] = np.nan
            times.append(capture)
            phases.append(values)
        times = np.asarray(times, dtype=np.int64)
        phases = np.asarray(phases)
        previous = np.searchsorted(times, times - 100_000_000, side="right") - 1
        valid = (previous >= 0) & (
            (times - times[np.maximum(previous, 0)]) <= 150_000_000
        )
        delta = np.full_like(phases, np.nan)
        delta[valid] = np.angle(np.exp(1j * (phases[valid] - phases[previous[valid]])))
        for wi, start in enumerate(starts):
            inside = (times >= start) & (times < start + 4_000_000_000)
            bins = (times[inside] - start) * 25 // 1_000_000_000
            for component in [np.sin(delta[inside]), np.cos(delta[inside])]:
                finite = np.isfinite(component)
                total = np.zeros((100, 242))
                count = np.zeros_like(total)
                np.add.at(total, bins, np.where(finite, component, 0))
                np.add.at(count, bins, finite)
                result[wi].append(
                    np.divide(
                        total, count, out=np.full_like(total, np.nan), where=count > 0
                    )
                )
    return np.asarray(result, dtype=np.float32)



def test_phase_native_matches_independent_integer_clock_reference(native_record):
    from fall_detection import _radio_native as core

    start = 10_000_000_000
    rows = []
    for i in range(110):
        record, _ = native_record(i + 1, weak=i % 3 == 0, bad=i % 17 == 0)
        rows.extend(
            (record, rx, start - 150_000_000 + i * 40_000_000) for rx in range(4)
        )
    reference = reference_phase_windows(rows, [start, start + 13_791_235])
    for kernel in ["scalar", "auto"]:
        native = core.CnnPreprocessor(
            [0.0] * 968, [1.0] * 968, kernel=kernel, representation="phase_change"
        )
        try:
            for wi, offset in enumerate([0, 13_791_235]):
                window = native.build(list(reversed(rows)), start + offset)
                raw = np.frombuffer(window.raw_bytes(), dtype="=f4").reshape(
                    8, 100, 242
                )
                np.testing.assert_allclose(
                    raw, reference[wi], atol=1e-6, equal_nan=True
                )
                tensor = np.frombuffer(window.tensor_bytes(), dtype="=f4").reshape(
                    16, 100, 242
                )
                np.testing.assert_array_equal(tensor, np.concatenate([np.nan_to_num(raw), np.isfinite(raw)], axis=-3).astype("float32"))
        finally:
            native.close()



def test_phase_maximum_lag_accepts_exact_150_ms_and_rejects_one_ns_more(native_record):
    from fall_detection import _radio_native as core

    record, _ = native_record()
    start = 10_000_000_123
    native = core.CnnPreprocessor(
        [0.0] * 968, [1.0] * 968, representation="phase_change"
    )
    try:
        for extra in [0, 1]:
            rows = [
                (record, rx, time)
                for rx in range(4)
                for time in [start - 150_000_000 - extra, start]
            ]
            window = native.build(rows, start)
            tensor = np.frombuffer(window.tensor_bytes(), dtype="=f4").reshape(
                16, 100, 242
            )
            assert np.all(tensor[8:, 0] == (1 if extra == 0 else 0))
    finally:
        native.close()



def test_phase_native_constructor_rejects_fitted_scaling():
    from fall_detection import _radio_native as core

    with pytest.raises(ValueError, match="identity parameters"):
        core.CnnPreprocessor([1.0] * 968, [2.0] * 968, representation="phase_change")
