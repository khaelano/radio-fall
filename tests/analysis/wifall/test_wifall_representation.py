"""WiFall window representations: smoothing, relative amplitude and features."""

import numpy as np

from fall_detection.analysis.wifall.representation import (
    _entropy_bits,
    receiver_representation,
    represent_windows,
    weighted_moving_average,
)

SETTINGS = {"sample_rate_hz": 10, "smoothing_samples": 3, "entropy_bins": 16}


def test_weighted_moving_average_equation_and_segment_start():
    np.testing.assert_allclose(
        weighted_moving_average(np.array([2, 5, 8, 11]), 3), [2, 4, 6, 9]
    )
    columns = np.array([[2, 1], [5, 1], [8, 4], [11, 4]])
    np.testing.assert_allclose(weighted_moving_average(columns, 3)[:, 0], [2, 4, 6, 9])


def test_entropy_matches_histogram_on_each_columns_own_range():
    values = np.random.default_rng(1).normal(size=(50, 3))
    expected = []
    for column in values.T:
        counts = np.histogram(column, bins=16)[0]
        probability = counts[counts > 0] / len(column)
        expected.append(-np.sum(probability * np.log2(probability)))
    np.testing.assert_allclose(_entropy_bits(values, 16), expected)
    np.testing.assert_allclose(_entropy_bits(np.ones((10, 2)), 16), 0)


def test_receiver_representation_is_independent_of_receiver_gain():
    rng = np.random.default_rng(2)
    window = 10 + rng.normal(0, 1, (40, 5))
    first = receiver_representation(window, **SETTINGS)
    second = receiver_representation(7 * window, **SETTINGS)
    for one, other in zip(first, second, strict=True):
        np.testing.assert_allclose(one, other)
    constant = receiver_representation(np.full((40, 5), 3.0), **SETTINGS)
    np.testing.assert_allclose(constant[0], 0, atol=1e-12)
    np.testing.assert_allclose(constant[1], 0, atol=1e-12)
    np.testing.assert_allclose(constant[2], 0, atol=1e-12)


def test_represent_windows_leaves_dropped_receivers_missing():
    windows = np.full((2, 20, 3, 4), 5.0)
    windows[1, :, 2] = np.nan
    batch = represent_windows(windows, **SETTINGS)
    np.testing.assert_array_equal(batch.present, [[True] * 3, [True, True, False]])
    assert np.isnan(batch.streams[1, :, 2]).all()
    assert len(batch.take(np.array([1]))) == 1
