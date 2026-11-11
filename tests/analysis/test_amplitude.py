"""Independent NumPy reference checks for the offline native Hampel filter."""

import numpy as np
import pytest

from fall_detection.analysis.amplitude import hampel_subcarriers, normalize_subcarriers


def reference(values, times, window=0.1, minimum=5, threshold=5.0):
    output = values.copy()
    mask = np.zeros(values.shape, dtype=bool)
    for row, time in enumerate(times):
        selected = (times >= time - window / 2) & (times <= time + window / 2)
        for col in range(values.shape[1]):
            samples = values[selected, col]
            samples = samples[np.isfinite(samples)]
            if len(samples) < minimum or not np.isfinite(values[row, col]):
                continue
            middle = np.median(samples)
            mad = np.median(np.abs(samples - middle))
            if mad > 0 and abs(values[row, col] - middle) > threshold * 1.4826 * mad:
                output[row, col] = middle
                mask[row, col] = True
    return output, mask


@pytest.mark.parametrize(
    "parallel,simd", [(False, False), (False, True), (True, False), (True, True)]
)
def test_hampel_subcarriers_matches_reference(parallel, simd):
    rng = np.random.default_rng(42)
    values = rng.normal(size=(121, 11))
    values[rng.random(values.shape) < 0.2] = np.nan
    values[:, 0] = np.nan
    values[:, 1] = 3.0
    values[50, 2:] = 100
    times = np.cumsum(rng.choice([0, 0.005, 0.01, 0.03], size=len(values)))
    original = values.copy()
    expected, mask = reference(values, times)
    actual, replaced = hampel_subcarriers(values, times, parallel=parallel, simd=simd)
    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(replaced, mask)
    np.testing.assert_array_equal(values, original)
    assert replaced.sum() > 0


@pytest.mark.parametrize("shape", [(0, 3), (3, 0), (1, 1)])
def test_hampel_subcarriers_empty_or_short(shape):
    values = np.zeros(shape)
    actual, replaced = hampel_subcarriers(values, np.arange(shape[0], dtype=float))
    np.testing.assert_array_equal(actual, values)
    assert not replaced.any()


def test_hampel_subcarriers_boundaries_and_noncontiguous_input():
    values = np.arange(45, dtype=float).reshape(9, 5)[:, ::2]
    values[4, 1] = 1000
    times = np.arange(9) / 32
    expected, mask = reference(values, times, window=0.25, minimum=2, threshold=1)
    actual, replaced = hampel_subcarriers(
        values, times, window_seconds=0.25, min_periods=2, threshold=1
    )
    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(replaced, mask)


@pytest.mark.parametrize("times", [[0, -1], [0, np.nan], [0, np.inf]])
def test_hampel_subcarriers_rejects_invalid_times(times):
    with pytest.raises(ValueError, match="finite and sorted"):
        hampel_subcarriers(np.zeros((2, 3)), times)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"window_seconds": 0},
        {"window_seconds": np.nan},
        {"min_periods": 0},
        {"threshold": -1},
        {"threshold": np.inf},
    ],
)
def test_hampel_subcarriers_rejects_invalid_parameters(kwargs):
    with pytest.raises(ValueError):
        hampel_subcarriers(np.zeros((2, 3)), [0, 1], **kwargs)


def test_hampel_subcarriers_rejects_bad_shape():
    with pytest.raises(ValueError, match="Expected amplitude"):
        hampel_subcarriers(np.zeros((2, 3)), [0])


def test_hampel_subcarriers_zero_mad_and_exact_threshold():
    values = np.array([[0, -1], [0, 0], [100, 0], [0, 1], [0, 1.4826]])
    # All timestamps equal: inclusive windows contain every sample. Column
    # zero has zero MAD; column one has a center exactly at the threshold.
    actual, replaced = hampel_subcarriers(
        values,
        np.zeros(5),
        min_periods=5,
        threshold=1,
    )
    np.testing.assert_array_equal(actual, values)
    assert not replaced.any()


def test_hampel_subcarriers_rejects_infinity_and_truncated_bytes():
    from fall_detection._radio_native import hampel_filter

    with pytest.raises(ValueError, match="finite values or NaN"):
        hampel_subcarriers(np.array([[np.inf]]), [0])
    with pytest.raises(ValueError, match="shape"):
        hampel_filter(b"short", np.array([0.0]).tobytes(), 1)


def test_normalize_subcarriers_preserves_masks_and_constants():
    values = np.array([[np.nan, 3, 0], [np.nan, 3, 5], [np.nan, np.nan, 10]])
    actual, lower, upper = normalize_subcarriers(values)
    np.testing.assert_array_equal(
        actual, [[np.nan, 0, -1], [np.nan, 0, 0], [np.nan, np.nan, 1]]
    )
    np.testing.assert_array_equal(lower, [np.nan, 3, 0])
    np.testing.assert_array_equal(upper, [np.nan, 3, 10])
