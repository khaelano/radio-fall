"""Amplitude preparation for the WiFall adaptation (paper equations 8 and 9)."""

import numpy as np


def validate_amplitudes(values: np.ndarray, *, ndim: int) -> np.ndarray:
    """Validate finite nonnegative amplitudes without imputing missing data.

    Args:
        values: Amplitude array with time, stream and tone axes.
        ndim: Required number of dimensions, including any batch axis.

    Returns:
        Float64 view or copy of the input.

    Raises:
        ValueError: If shape, finiteness or amplitude domain is invalid.
    """
    result = np.asarray(values, dtype=np.float64)
    if result.ndim != ndim or any(size == 0 for size in result.shape):
        raise ValueError(f"Expected a nonempty {ndim}-dimensional amplitude array")
    if not np.isfinite(result).all() or np.any(result < 0):
        raise ValueError("Amplitudes must be finite and nonnegative")
    return result


def weighted_moving_average(values: np.ndarray, samples: int) -> np.ndarray:
    """Apply causal weights m newest through 1 oldest along the first axis.

    The paper leaves startup undefined. Here each segment starts with the
    available prefix and uses weights k newest through 1 oldest for k < m.
    Samples from another window or recording never contribute.

    Args:
        values: Nonempty amplitude array, with time as the first axis.
        samples: Positive integral trailing neighborhood length.

    Returns:
        Smoothed array with the same shape.
    """
    array = np.asarray(values, dtype=np.float64)
    if (
        array.ndim < 1
        or len(array) == 0
        or not np.isfinite(array).all()
        or isinstance(samples, bool)
        or not isinstance(samples, (int, np.integer))
        or samples < 1
    ):
        raise ValueError("Expected finite samples and a positive integer neighborhood")
    result = np.empty_like(array)
    for index in range(len(array)):
        start = max(0, index + 1 - samples)
        weights = np.arange(1, index - start + 2, dtype=np.float64)
        result[index] = np.tensordot(weights, array[start : index + 1], axes=1)
        result[index] /= weights.sum()
    return result


def aggregate_streams(
    amplitudes: np.ndarray, frequency_weights: np.ndarray | None = None
) -> np.ndarray:
    """Aggregate tones as mean((f_j/f_0) * amplitude_j), as in equation 8.

    Args:
        amplitudes: Array with subcarriers on the last axis.
        frequency_weights: Positive tone frequency ratios; ones when omitted.

    Returns:
        Array with the last axis reduced, without normalizing by weight sum.
    """
    values = np.asarray(amplitudes, dtype=np.float64)
    if values.ndim < 1 or values.shape[-1] == 0:
        raise ValueError("A nonempty tone axis is required")
    weights = (
        np.ones(values.shape[-1])
        if frequency_weights is None
        else np.asarray(frequency_weights, dtype=np.float64)
    )
    if (
        weights.shape != (values.shape[-1],)
        or not np.isfinite(weights).all()
        or np.any(weights <= 0)
    ):
        raise ValueError("frequency_weights must contain one positive ratio per tone")
    return np.mean(values * weights, axis=-1)
