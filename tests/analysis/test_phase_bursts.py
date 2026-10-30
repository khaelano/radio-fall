"""Verify burst measurements against known traces, gaps, and censoring."""

import numpy as np
import pytest

from fall_detection.analysis.phase_bursts import summarize_phase_bursts


@pytest.fixture
def trace():
    seconds = np.arange(300) / 100
    scores = np.full(300, 0.1)
    scores[120:161] = 1.1
    intervals = {"countdown": (0, 1), "action": (1, 2), "recovery": (2, 3)}
    return seconds, scores, intervals


def test_summarize_phase_bursts_measures_known_burst_and_rise(trace):
    result = summarize_phase_bursts(*trace)
    assert result["usable"]
    assert result["threshold_rad"] == pytest.approx(0.1)
    assert result["peak_excess_rad"] == pytest.approx(1.0)
    assert result["action_p95_excess_rad"] == pytest.approx(1.0)
    assert result["burst_count"] == 1
    assert result["longest_burst_s"] == pytest.approx(0.4)
    assert result["above_threshold_s"] == pytest.approx(0.4)
    assert result["action_supported_s"] == pytest.approx(0.99)
    assert result["active_fraction"] == pytest.approx(0.4 / 0.99)
    assert result["rise_10_90_s"] == pytest.approx(0.008)
    assert not result["peak_burst_left_censored"]
    assert not result["peak_burst_right_censored"]
    assert result["recovery_median_excess_rad"] == pytest.approx(0)


@pytest.mark.parametrize("missing", ["nan", "gap"])
def test_summarize_phase_bursts_breaks_runs_at_missing_data(trace, missing):
    seconds, scores, intervals = trace
    if missing == "nan":
        scores[140:150] = np.nan
    else:
        keep = ~((seconds >= 1.4) & (seconds < 1.5))
        seconds, scores = seconds[keep], scores[keep]
    result = summarize_phase_bursts(seconds, scores, intervals)
    assert result["burst_count"] == 2
    assert result["longest_burst_s"] == pytest.approx(0.19)
    assert result["above_threshold_s"] == pytest.approx(0.29)
    assert result["peak_burst_right_censored"]


def test_summarize_phase_bursts_distinguishes_no_burst_from_no_data(trace):
    seconds, scores, intervals = trace
    scores[:] = 0.1
    no_burst = summarize_phase_bursts(seconds, scores, intervals)
    assert no_burst["usable"]
    assert no_burst["burst_count"] == 0
    assert no_burst["longest_burst_s"] == 0
    assert no_burst["active_fraction"] == 0
    assert np.isnan(no_burst["rise_10_90_s"])
    scores[100:200] = np.nan
    no_data = summarize_phase_bursts(seconds, scores, intervals)
    assert not no_data["usable"]
    assert np.isnan(no_data["burst_count"])
    assert np.isnan(no_data["above_threshold_s"])


def test_summarize_phase_bursts_requires_countdown_and_marks_boundary_rise(trace):
    seconds, scores, intervals = trace
    scores[100:140] = 1.1
    censored = summarize_phase_bursts(seconds, scores, intervals)
    assert censored["peak_burst_left_censored"]
    assert np.isnan(censored["rise_10_90_s"])
    scores[:90] = np.nan
    no_baseline = summarize_phase_bursts(seconds, scores, intervals)
    assert not no_baseline["usable"]
    assert np.isnan(no_baseline["threshold_rad"])


def test_summarize_phase_bursts_limits_recovery_to_initial_window(trace):
    seconds, scores, intervals = trace
    scores[250:] = 2
    initial = summarize_phase_bursts(
        seconds, scores, intervals, recovery_window_seconds=0.4
    )
    assert initial["recovery_window_valid_scores"] == 40
    assert initial["recovery_median_excess_rad"] == pytest.approx(0)
    scores[200:230] = np.nan
    sparse = summarize_phase_bursts(
        seconds, scores, intervals, recovery_window_seconds=0.4
    )
    assert sparse["usable"]
    assert np.isnan(sparse["recovery_median_excess_rad"])


def test_summarize_phase_bursts_does_not_infer_time_support_from_packet_count(trace):
    _, scores, intervals = trace
    seconds = np.repeat([0.5, 1.5, 2.5], 100)
    result = summarize_phase_bursts(seconds, scores, intervals)
    assert result["action_valid_scores"] == 100
    assert result["action_supported_s"] == 0
    assert not result["usable"]
    assert np.isnan(result["above_threshold_s"])


def test_summarize_phase_bursts_rejects_overlapping_intervals(trace):
    seconds, scores, intervals = trace
    intervals["action"] = (0.9, 2)
    with pytest.raises(ValueError, match="disjoint"):
        summarize_phase_bursts(seconds, scores, intervals)
