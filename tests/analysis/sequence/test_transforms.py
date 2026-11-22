"""Checks for the difference transforms behind the sequence signal."""

import numpy as np

from fall_detection.analysis.sequence.transforms import (
    absolute_difference,
    squared_difference,
)


def test_absolute_difference_keeps_magnitude_and_preserves_gaps():
    values = np.array([[1.0], [4.0], [2.0], [np.nan], [5.0]])
    diff = absolute_difference(values)
    np.testing.assert_array_equal(diff[:, 0], [np.nan, 3, 2, np.nan, np.nan])
    np.testing.assert_array_equal(
        squared_difference(values)[:, 0], [np.nan, 9, 4, np.nan, np.nan]
    )
