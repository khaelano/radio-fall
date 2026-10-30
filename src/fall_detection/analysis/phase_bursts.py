"""Descriptive burst measurements on one receiver's phase-motion trace."""

from collections.abc import Mapping

import numpy as np


def summarize_phase_bursts(
    seconds: np.ndarray,
    scores: np.ndarray,
    intervals: Mapping[str, tuple[float, float]],
    *,
    threshold_quantile: float = 0.95,
    min_phase_scores: int = 20,
    max_gap_seconds: float = 0.05,
    recovery_window_seconds: float = 1.0,
) -> dict[str, float | int | bool]:
    """Summarize action bursts against the recording's countdown distribution.

    Args:
        seconds: Finite, nondecreasing packet times relative to attempt start.
        scores: Nonnegative circular changes in radians per lag. Missing scores
            and lag windows crossing phase boundaries must already be NaN.
        intervals: Exactly one positive countdown/action/recovery interval each,
            in seconds on the packet timeline, without overlap.
        threshold_quantile: Countdown quantile defining an above-baseline burst.
        min_phase_scores: Minimum finite countdown/action scores for usability.
            Recovery needs the same count within its initial observation window.
        max_gap_seconds: Largest supported inter-sample interval. Missing scores,
            duplicate times, and larger gaps break runs and duration support.
        recovery_window_seconds: Initial recovery window used for its median.

    Returns:
        Coverage, threshold, action strength, burst duration/count, rise time,
        and initial recovery measurements. Unusable measurements remain NaN.
        Durations sum only intervals with two finite endpoints; above-threshold
        duration requires both endpoints above threshold and is a lower bound.
        Rise time interpolates the first 10% and 90% crossings of excess over
        threshold in the run containing the action maximum. A missing preceding
        below-threshold sample makes that rise left-censored and unavailable.

    Raises:
        ValueError: Arrays, phase intervals, or parameters are invalid.
    """
    seconds = np.asarray(seconds, dtype=float)
    scores = np.asarray(scores, dtype=float)
    if seconds.ndim != 1 or scores.shape != seconds.shape:
        raise ValueError("Expected matching one-dimensional times and scores")
    if not np.isfinite(seconds).all() or np.any(np.diff(seconds) < 0):
        raise ValueError("Packet times must be finite and nondecreasing")
    if np.isinf(scores).any() or np.any(scores[np.isfinite(scores)] < 0):
        raise ValueError("Scores must be nonnegative or NaN")
    if not np.isfinite(threshold_quantile) or not 0 < threshold_quantile < 1:
        raise ValueError("threshold_quantile must lie between zero and one")
    if (
        not isinstance(min_phase_scores, int)
        or isinstance(min_phase_scores, bool)
        or min_phase_scores < 2
    ):
        raise ValueError("min_phase_scores must be an integer of at least two")
    if any(
        not np.isfinite(value) or value <= 0
        for value in (max_gap_seconds, recovery_window_seconds)
    ):
        raise ValueError("Gap and recovery window must be finite and positive")
    phases = ("countdown", "action", "recovery")
    if set(intervals) != set(phases):
        raise ValueError("Exactly countdown/action/recovery intervals are required")
    bounds = np.asarray([intervals[phase] for phase in phases], dtype=float)
    if (
        bounds.shape != (3, 2)
        or not np.isfinite(bounds).all()
        or np.any(bounds[:, 1] <= bounds[:, 0])
        or np.any(bounds[1:, 0] < bounds[:-1, 1])
    ):
        raise ValueError("Phase intervals must be positive, ordered, and disjoint")
    masks = {
        phase: (seconds >= start) & (seconds < stop)
        for phase, (start, stop) in zip(phases, bounds)
    }
    finite = np.isfinite(scores)
    result = {
        "usable": False,
        **{
            f"{phase}_valid_scores": int((mask & finite).sum())
            for phase, mask in masks.items()
        },
    }
    for name in (
        "baseline_median_rad",
        "threshold_rad",
        "action_p95_rad",
        "action_p95_excess_rad",
        "peak_excess_rad",
        "peak_delay_s",
        "action_supported_s",
        "action_supported_fraction",
        "above_threshold_s",
        "active_fraction",
        "burst_count",
        "longest_burst_s",
        "rise_10_90_s",
        "peak_burst_left_censored",
        "peak_burst_right_censored",
        "recovery_median_excess_rad",
    ):
        result[name] = np.nan
    recovery_start, recovery_stop = intervals["recovery"]
    recovery = (
        masks["recovery"]
        & finite
        & (seconds < min(recovery_stop, recovery_start + recovery_window_seconds))
    )
    result["recovery_window_valid_scores"] = int(recovery.sum())
    if result["countdown_valid_scores"] < min_phase_scores:
        return result
    baseline = scores[masks["countdown"] & finite]
    threshold = float(np.quantile(baseline, threshold_quantile))
    result["baseline_median_rad"] = float(np.median(baseline))
    result["threshold_rad"] = threshold
    if recovery.sum() >= min_phase_scores:
        result["recovery_median_excess_rad"] = float(
            np.median(scores[recovery]) - result["baseline_median_rad"]
        )
    if result["action_valid_scores"] < min_phase_scores:
        return result
    selected = np.flatnonzero(masks["action"])
    t, y = seconds[selected], scores[selected]
    valid = np.isfinite(y)
    dt = np.diff(t)
    connected = (dt > 0) & (dt <= max_gap_seconds)
    supported = connected & valid[:-1] & valid[1:]
    support = float(dt[supported].sum())
    result["action_supported_s"] = support
    result["action_supported_fraction"] = support / (
        intervals["action"][1] - intervals["action"][0]
    )
    if support == 0:
        return result
    result["usable"] = True
    result["action_p95_rad"] = float(np.nanquantile(y, 0.95))
    result["action_p95_excess_rad"] = result["action_p95_rad"] - threshold
    peak = int(np.nanargmax(y))
    result["peak_excess_rad"] = float(y[peak] - threshold)
    result["peak_delay_s"] = float(t[peak] - intervals["action"][0])
    above = valid & (y > threshold)
    active = supported & above[:-1] & above[1:]
    result["above_threshold_s"] = float(dt[active].sum())
    result["active_fraction"] = result["above_threshold_s"] / support
    starts = np.flatnonzero(above & ~np.r_[False, above[:-1] & connected])
    ends = np.flatnonzero(above & ~np.r_[above[1:] & connected, False])
    result["burst_count"] = len(starts)
    result["longest_burst_s"] = float(np.max(t[ends] - t[starts], initial=0))
    if not above[peak]:
        return result
    run = int(np.flatnonzero((starts <= peak) & (ends >= peak))[0])
    start, end = int(starts[run]), int(ends[run])
    left_censored = start == 0 or not (connected[start - 1] and valid[start - 1])
    right_censored = end == len(y) - 1 or not (connected[end] and valid[end + 1])
    result["peak_burst_left_censored"] = bool(left_censored)
    result["peak_burst_right_censored"] = bool(right_censored)
    if not left_censored:
        # Only interpolate scalar crossings between observed samples; no trace
        # resampling, smoothing, or bridging of missing packets is performed.
        rise_y, rise_t = y[start - 1 : peak + 1], t[start - 1 : peak + 1]
        crossings = []
        for fraction in (0.1, 0.9):
            level = threshold + fraction * (y[peak] - threshold)
            upper = int(np.flatnonzero(rise_y >= level)[0])
            lower = upper - 1
            weight = (level - rise_y[lower]) / (rise_y[upper] - rise_y[lower])
            crossings.append(rise_t[lower] + weight * (rise_t[upper] - rise_t[lower]))
        result["rise_10_90_s"] = float(crossings[1] - crossings[0])
    return result
