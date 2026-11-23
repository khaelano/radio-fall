"""Checks for the main-burst locator behind burst training labels."""

import numpy as np
import pytest

from fall_detection.analysis.sequence.bursts import (
    main_burst,
    motion_envelope,
    running_median,
)


def test_running_median_ignores_missing_values():
    values = np.array([1.0, np.nan, 3.0, 100.0, 5.0])
    smoothed = running_median(values, 3, min_count=2)
    np.testing.assert_allclose(smoothed, [np.nan, 2.0, 51.5, 5.0, 52.5])
    with pytest.raises(ValueError, match="odd"):
        running_median(values, 4)


def test_motion_envelope_rises_with_change_and_skips_gaps():
    amplitude = np.full((40, 2, 3), 10.0)
    amplitude[20:30] *= np.where(np.arange(10) % 2, 2.0, 1.0)[:, None, None]
    amplitude[5:8, 1] = np.nan  # receiver 2 missing
    envelope = motion_envelope(amplitude, smooth_samples=3)
    assert envelope.shape == (40,)
    assert np.nanmax(envelope[22:28]) > 1.0
    assert np.nanmax(envelope[:18]) == 0.0


def test_main_burst_finds_peak_and_half_prominence_extent():
    envelope = np.zeros(100)
    envelope[40:50] = [1, 2, 4, 6, 8, 6, 4, 3, 1, 0]
    envelope[60] = np.nan  # gaps inside the search range are skipped
    phase = np.array(["preparation"] * 30 + ["action"] * 30 + ["resting"] * 40)
    burst = main_burst(envelope, phase, rate_hz=10, before_seconds=0.5)
    assert burst["peak"] == 44
    assert (burst["start"], burst["end"]) == (42, 46)  # values >= 4
    assert burst["prominence"] == 8.0
    assert main_burst(envelope, np.array(["preparation"] * 100), rate_hz=10) is None
