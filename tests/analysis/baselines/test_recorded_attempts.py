"""Bounded gap interpolation shared by the classical baselines."""

import numpy as np
import pytest

from fall_detection.analysis.baselines._recorded_attempts import fill_short_gaps


def test_fill_short_gaps_brackets_bounds_and_preserves_source():
    values = np.array(
        [[np.nan, 1], [2, np.nan], [np.nan, 3], [4, np.nan], [np.nan, np.nan]]
    )
    original = values.copy()
    result = fill_short_gaps(values, sample_rate_hz=10, max_gap_seconds=0.2)
    np.testing.assert_array_equal(values, original)
    np.testing.assert_array_equal(
        result, [[np.nan, 1], [2, 2], [3, 3], [4, np.nan], [np.nan, np.nan]]
    )
    np.testing.assert_array_equal(
        fill_short_gaps(values, sample_rate_hz=10, max_gap_seconds=0.19), original
    )


@pytest.mark.parametrize(
    "values,settings",
    [
        (np.ones((4, 1)), {"sample_rate_hz": 0}),
        (np.ones((4, 1)), {"max_gap_seconds": float("nan")}),
        (np.array([[-1.0], [2]]), {}),
        (np.array([[np.inf], [2]]), {}),
    ],
)
def test_fill_short_gaps_rejects_invalid_inputs(values, settings):
    with pytest.raises(ValueError, match="amplitudes"):
        fill_short_gaps(values, **settings)
