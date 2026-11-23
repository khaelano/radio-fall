"""Checks for the difference transforms behind the sequence signal."""

import numpy as np

from fall_detection.analysis.sequence.transforms import (
    absolute_difference,
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
