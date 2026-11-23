"""Locate the main motion burst of an attempt for training labels.

Collection cues bound an activity only loosely: a fall cue spans seconds
before the fall starts and the lying after it. The main burst narrows a fall
attempt's positive training windows to the movement itself. The envelope is
the burst screen's (``docs/reports/tone-pooling-2026-11-23.md``): the mean
over present tones and receivers of the squared change in log amplitude,
which skips missing samples instead of filling them.
"""

from __future__ import annotations

import numpy as np

ENVELOPE_SCALE = 1000.0
"""Scales the squared log ratios before ``log1p`` in :func:`motion_envelope`."""


def running_median(values: np.ndarray, width: int, *, min_count: int = 3) -> np.ndarray:
    """Centred running median that ignores NaN.

    Args:
        values: One-dimensional samples; NaN marks missing values.
        width: Odd window length in samples.
        min_count: Fewest finite values a window needs; fewer gives NaN.

    Returns:
        The smoothed samples, with the input length.

    Raises:
        ValueError: If ``width`` is not a positive odd number.
    """
    if width < 1 or width % 2 == 0:
        raise ValueError("width must be a positive odd number")
    array = np.asarray(values, dtype=np.float64)
    half = width // 2
    padded = np.pad(array, half, constant_values=np.nan)
    windows = np.lib.stride_tricks.sliding_window_view(padded, width)
    counts = np.isfinite(windows).sum(axis=1)
    result = np.full(len(array), np.nan)
    enough = counts >= min_count
    if enough.any():
        result[enough] = np.nanmedian(windows[enough], axis=1)
    return result


def motion_envelope(amplitude: np.ndarray, *, smooth_samples: int = 15) -> np.ndarray:
    """Return the smoothed motion envelope of one segment.

    Args:
        amplitude: Positive amplitudes ``[time, receiver, tone]``; NaN marks
            missing samples.
        smooth_samples: Width of the running median (15 samples is 0.125 s
            at 120 Hz).

    Returns:
        ``log1p(1000 * mean over finite tones and receivers of
        (ln a[t] - ln a[t - 1]) ** 2)``, smoothed; NaN where no change is
        finite.

    Raises:
        ValueError: If the amplitudes are not three-dimensional.
    """
    array = np.asarray(amplitude, dtype=np.float64)
    if array.ndim != 3:
        raise ValueError("Expected [time, receiver, tone] amplitudes")
    with np.errstate(divide="ignore", invalid="ignore"):
        logged = np.log(array)
    change = np.full(array.shape, np.nan)
    change[1:] = (logged[1:] - logged[:-1]) ** 2
    finite = np.isfinite(change)
    count = finite.sum(axis=(1, 2))
    total = np.where(finite, change, 0).sum(axis=(1, 2))
    mean = np.divide(total, count, out=np.full(len(array), np.nan), where=count > 0)
    return running_median(np.log1p(ENVELOPE_SCALE * mean), smooth_samples)


def main_burst(
    envelope: np.ndarray,
    phase: np.ndarray,
    *,
    rate_hz: float,
    before_seconds: float = 0.5,
    after_seconds: float = 1.0,
    floor_percentile: float = 20.0,
) -> dict[str, float | int] | None:
    """Find the strongest burst around an attempt's action cue.

    The quiet floor is a low percentile of the envelope during
    ``preparation`` (the whole segment when that phase is absent). The peak
    is searched from ``before_seconds`` before the action cue to
    ``after_seconds`` after it. The burst extends from the peak while the
    envelope stays at or above half its prominence; missing samples do not
    end it.

    Args:
        envelope: Output of :func:`motion_envelope`.
        phase: Collection phase of every sample.
        rate_hz: Sampling rate.
        before_seconds: Search margin before the action cue.
        after_seconds: Search margin after the action cue.
        floor_percentile: Percentile of the preparation envelope used as floor.

    Returns:
        Sample indices ``peak``, ``start`` and ``end`` (inclusive), and the
        ``floor`` and ``prominence``; None without an action cue, a finite
        envelope in the search range, or a peak above the floor.
    """
    values = np.asarray(envelope, dtype=np.float64)
    phase = np.asarray(phase)
    action = np.flatnonzero(phase == "action")
    if not len(action):
        return None
    preparation = values[phase == "preparation"]
    source = preparation if np.isfinite(preparation).any() else values
    if not np.isfinite(source).any():
        return None
    floor = float(np.nanpercentile(source, floor_percentile))
    low = max(0, action[0] - round(before_seconds * rate_hz))
    high = min(len(values), action[-1] + 1 + round(after_seconds * rate_hz))
    search = values[low:high]
    if not np.isfinite(search).any():
        return None
    peak = low + int(np.nanargmax(search))
    prominence = float(values[peak] - floor)
    if not prominence > 0:
        return None
    half = floor + prominence / 2

    def extend(step: int) -> int:
        index = peak
        while 0 <= index + step < len(values) and not (
            np.isfinite(values[index + step]) and values[index + step] < half
        ):
            index += step
        return index

    return {
        "peak": peak,
        "start": extend(-1),
        "end": extend(1),
        "floor": floor,
        "prominence": prominence,
    }
