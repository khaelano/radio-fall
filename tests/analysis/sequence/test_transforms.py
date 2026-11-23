"""Checks for the difference transforms behind the sequence signal."""

import numpy as np
import pytest

from fall_detection.analysis.sequence.transforms import (
    absolute_difference,
    lagged_squared_difference,
    quiet_floor,
    squared_difference,
    tone_mean_squared_log_ratio,
)


def test_absolute_difference_keeps_magnitude_and_preserves_gaps():
    values = np.array([[1.0], [4.0], [2.0], [np.nan], [5.0]])
    diff = absolute_difference(values)
    np.testing.assert_array_equal(diff[:, 0], [np.nan, 3, 2, np.nan, np.nan])
    np.testing.assert_array_equal(
        squared_difference(values)[:, 0], [np.nan, 9, 4, np.nan, np.nan]
    )


def test_tone_mean_squared_log_ratio_ignores_gain_and_missing_tones():
    base = np.array([[1.0, 2.0], [2.0, 2.0], [np.nan, np.nan], [4.0, np.nan]])
    values = np.stack([base, 10 * base], axis=1)  # receiver 2 has 10x the gain
    pooled = tone_mean_squared_log_ratio(values)
    assert pooled.shape == (4, 2, 1)
    expected = [np.nan, np.log(2) ** 2 / 2, np.nan, np.nan]
    np.testing.assert_allclose(pooled[:, 0, 0], expected)
    np.testing.assert_allclose(pooled[:, 1, 0], expected)


def test_quiet_floor_skips_missing_samples_and_unseen_features():
    first = np.array([[1.0, np.nan], [3.0, np.nan]])
    second = np.array([[5.0, np.nan]])
    np.testing.assert_array_equal(quiet_floor([first, second]), [3.0, 0.0])


def test_lagged_squared_difference_spans_lag_and_preserves_gaps():
    values = np.array([[1.0], [2.0], [4.0], [np.nan], [8.0]])
    np.testing.assert_array_equal(
        lagged_squared_difference(values, 2)[:, 0], [np.nan, np.nan, 9, np.nan, 16]
    )
    np.testing.assert_array_equal(
        lagged_squared_difference(values, 1), squared_difference(values)
    )
    with pytest.raises(ValueError, match="positive"):
        lagged_squared_difference(values, 0)
