"""Per-receiver window representations for the WiFall adaptation (paper §4).

For each receiver of a window, tones are scaled to relative amplitude (each
divided by its window mean, since the C5 receivers are separate radios with
their own gain) and smoothed with the causal weighted moving average of
equation 9. From the smoothed tones come six statistics, three singular values
of the centered window, and the stream used by the activity detector. WiFall
averages the tones into that stream (equation 8), but motion raises some tones
while lowering others, so across 120 tones the average cancels it: on the
9 November 13:15 session its 2 s standard deviation was only 1.14 times the
resting value during falls, against 1.54 times for the first principal
component. The stream is therefore the window's first principal component.
Only the motion period needs the training-only resting profile and is left to
the detector.

Representations are computed once per window, independent of other windows
and of labels, so computing them before the train/test split leaks nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from threadpoolctl import threadpool_limits

STATISTIC_NAMES = (
    "normalized_std",
    "signal_offset",
    "median_absolute_deviation",
    "interquartile_range",
    "signal_entropy_bits",
    "mean_absolute_velocity",
)
"""Statistics stored per receiver; the detector adds the motion period."""

SINGULAR_VALUE_NAMES = ("singular_value_1", "singular_value_2", "singular_value_3")


@dataclass(frozen=True)
class Representations:
    """Representations of a batch of windows; dropped receivers are NaN.

    Attributes:
        statistics: ``[window, receiver, statistic]`` in STATISTIC_NAMES order.
        singular_values: ``[window, receiver, 3]`` leading singular values.
        streams: First principal component of the smoothed relative tones
            ``[window, time, receiver]``.
    """

    statistics: np.ndarray
    singular_values: np.ndarray
    streams: np.ndarray

    def __post_init__(self) -> None:
        count, receivers = self.statistics.shape[:2]
        if (
            self.statistics.shape[2:] != (len(STATISTIC_NAMES),)
            or self.singular_values.shape != (count, receivers, 3)
            or self.streams.ndim != 3
            or self.streams.shape[0] != count
            or self.streams.shape[2] != receivers
        ):
            raise ValueError("Representation arrays disagree in shape")

    def __len__(self) -> int:
        """Return the number of windows."""
        return len(self.statistics)

    @property
    def present(self) -> np.ndarray:
        """Return ``[window, receiver]`` flags for receivers with data."""
        return np.isfinite(self.statistics).all(axis=2)

    def take(self, indices: np.ndarray) -> Representations:
        """Return the representations of the selected windows.

        Args:
            indices: Window indices or a boolean mask.

        Returns:
            A new batch in the given order.
        """
        return Representations(
            self.statistics[indices],
            self.singular_values[indices],
            self.streams[indices],
        )


def weighted_moving_average(values: np.ndarray, samples: int) -> np.ndarray:
    """Apply causal weights m newest through 1 oldest along the first axis.

    The paper leaves startup undefined. Each segment starts with the available
    prefix and uses weights k newest through 1 oldest for k < m. Samples from
    another window never contribute.

    Args:
        values: Finite array with time as the first axis.
        samples: Positive integral trailing neighborhood length m.

    Returns:
        Smoothed array with the same shape.

    Raises:
        ValueError: If values are not finite or m is not a positive integer.
    """
    array = np.asarray(values, dtype=np.float64)
    if (
        array.ndim < 1
        or not len(array)
        or not np.isfinite(array).all()
        or isinstance(samples, bool)
        or not isinstance(samples, (int, np.integer))
        or samples < 1
    ):
        raise ValueError("Expected finite samples and a positive integer neighborhood")
    count = np.minimum(np.arange(1, len(array) + 1), samples)
    shape = (len(array),) + (1,) * (array.ndim - 1)
    total = np.zeros_like(array)
    for lag in range(min(samples, len(array))):
        weight = np.maximum(count[lag:] - lag, 0).reshape((-1,) + shape[1:])
        total[lag:] += weight * array[: len(array) - lag]
    return total / (count * (count + 1) / 2).reshape(shape)


def _entropy_bits(values: np.ndarray, bins: int) -> np.ndarray:
    """Return base-two histogram entropy of each column on its own range."""
    low, high = values.min(axis=0), values.max(axis=0)
    span = np.where(high > low, high - low, 1.0)
    index = np.minimum(((values - low) / span * bins).astype(int), bins - 1)
    counts = np.zeros((bins, values.shape[1]))
    np.add.at(counts, (index, np.arange(values.shape[1])), 1)
    probability = counts / len(values)
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = np.where(probability > 0, probability * np.log2(probability), 0.0)
    return -terms.sum(axis=0)


def receiver_representation(
    values: np.ndarray,
    *,
    sample_rate_hz: float,
    smoothing_samples: int,
    entropy_bins: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Represent one receiver's window.

    Args:
        values: Finite nonnegative amplitudes ``[time, tone]``.
        sample_rate_hz: Sampling frequency, for the velocity's units.
        smoothing_samples: Neighborhood m of equation 9.
        entropy_bins: Histogram bins for the signal entropy.

    Returns:
        Statistics in STATISTIC_NAMES order, three singular values divided by
        the square root of the window length, and the first principal
        component as the activity stream.

    Raises:
        ValueError: If the window is too small or not finite and nonnegative.
    """
    amplitude = np.asarray(values, dtype=np.float64)
    if (
        amplitude.ndim != 2
        or min(amplitude.shape) < 3
        or not np.isfinite(amplitude).all()
        or np.any(amplitude < 0)
    ):
        raise ValueError(
            "Receiver windows must be finite nonnegative [time, tone], at least 3x3"
        )
    means = amplitude.mean(axis=0)
    relative = np.divide(
        amplitude, means, out=np.zeros_like(amplitude), where=means > 0
    )
    smoothed = weighted_moving_average(relative, smoothing_samples)
    level = smoothed.mean(axis=0)
    deviation = smoothed.std(axis=0)
    median = np.median(smoothed, axis=0)
    quartiles = np.quantile(smoothed, [0.25, 0.75], axis=0)
    statistics = np.array(
        [
            np.divide(deviation, level, out=np.zeros_like(level), where=level > 0),
            np.ptp(smoothed, axis=0),
            np.median(np.abs(smoothed - median), axis=0),
            quartiles[1] - quartiles[0],
            _entropy_bits(smoothed, entropy_bins),
            np.abs(np.diff(smoothed, axis=0)).mean(axis=0) * sample_rate_hz,
        ]
    ).mean(axis=1)
    centered = smoothed - smoothed.mean(axis=0)
    # A window's SVD is small; more BLAS threads only slow it down.
    with threadpool_limits(limits=1, user_api="blas"):
        left, singular, _ = np.linalg.svd(centered, full_matrices=False)
    # The component's sign is arbitrary; fixing it keeps streams comparable.
    component = left[:, 0] * singular[0]
    if component[np.argmax(np.abs(component))] < 0:
        component = -component
    return statistics, singular[:3] / np.sqrt(len(smoothed)), component


def represent_windows(
    windows: np.ndarray,
    *,
    sample_rate_hz: float,
    smoothing_samples: int = 5,
    entropy_bins: int = 16,
) -> Representations:
    """Represent raw amplitude windows, leaving dropped receivers as NaN.

    Args:
        windows: Amplitudes ``[window, time, receiver, tone]``; a dropped
            receiver is all NaN in its window.
        sample_rate_hz: Sampling frequency.
        smoothing_samples: Neighborhood m of equation 9.
        entropy_bins: Histogram bins for the signal entropy.

    Returns:
        The batch of representations.
    """
    values = np.asarray(windows, dtype=np.float64)
    if values.ndim != 4:
        raise ValueError("Windows must be [window, time, receiver, tone]")
    count, time, receivers, _ = values.shape
    statistics = np.full((count, receivers, len(STATISTIC_NAMES)), np.nan)
    singular = np.full((count, receivers, 3), np.nan)
    streams = np.full((count, time, receivers), np.nan, dtype=np.float32)
    for window in range(count):
        for receiver in range(receivers):
            block = values[window, :, receiver]
            if np.isnan(block).all():
                continue
            statistics[window, receiver], singular[window, receiver], stream = (
                receiver_representation(
                    block,
                    sample_rate_hz=sample_rate_hz,
                    smoothing_samples=smoothing_samples,
                    entropy_bins=entropy_bins,
                )
            )
            streams[window, :, receiver] = stream
    return Representations(statistics, singular, streams)
