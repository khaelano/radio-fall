"""Explicit feature definitions where WiFall gives names but omits formulas.

Statistics are computed per tone and averaged within each stream. Normalized
STD is STD/mean; signal offset is max-min; MAD is median absolute deviation;
entropy is base-two histogram entropy on each tone's own amplitude range;
velocity is mean absolute first difference per second. Motion period is the
number of LOF-active samples in the stream divided by sample rate. These are
documented adaptation choices, not recovered author implementation details.

The paper does not explain how its three SVD values connect to its seven
statistics. They are implemented as alternative representations, not combined.
"""

import numpy as np

STATISTIC_NAMES = (
    "normalized_std",
    "signal_offset",
    "motion_period_seconds",
    "median_absolute_deviation",
    "interquartile_range",
    "signal_entropy_bits",
    "mean_absolute_velocity",
)


def statistical_features(
    window: np.ndarray,
    active: np.ndarray,
    *,
    sample_rate_hz: float,
    entropy_bins: int,
) -> np.ndarray:
    """Extract seven features for each stream of a prepared window.

    Args:
        window: Finite amplitudes shaped [time, stream, tone].
        active: Boolean per-sample LOF anomalies shaped [time, stream].
        sample_rate_hz: Sampling frequency for duration and derivative units.
        entropy_bins: Number of amplitude bins for Shannon entropy.

    Returns:
        Flattened features ordered by stream, then STATISTIC_NAMES.
    """
    means = window.mean(axis=0)
    std = window.std(axis=0)
    normalized = np.divide(std, means, out=np.zeros_like(std), where=means != 0)
    median = np.median(window, axis=0)
    entropy = np.empty(window.shape[1:])
    for stream in range(window.shape[1]):
        for tone in range(window.shape[2]):
            counts = np.histogram(window[:, stream, tone], bins=entropy_bins)[0]
            probabilities = counts[counts > 0] / len(window)
            entropy[stream, tone] = -np.sum(probabilities * np.log2(probabilities))
    stats = (
        normalized.mean(axis=-1),
        np.ptp(window, axis=0).mean(axis=-1),
        active.sum(axis=0) / sample_rate_hz,
        np.median(np.abs(window - median), axis=0).mean(axis=-1),
        (np.quantile(window, 0.75, axis=0) - np.quantile(window, 0.25, axis=0)).mean(
            axis=-1
        ),
        entropy.mean(axis=-1),
        (np.abs(np.diff(window, axis=0)).mean(axis=0) * sample_rate_hz).mean(axis=-1),
    )
    return np.stack(stats, axis=-1).ravel()


def singular_value_features(window: np.ndarray) -> np.ndarray:
    """Return the leading three singular values of the uncentered CSI matrix.

    Args:
        window: Prepared amplitudes shaped [time, stream, tone].

    Returns:
        Three singular values in descending order.

    Raises:
        ValueError: If the matrix has fewer than three singular values.
    """
    matrix = window.reshape(len(window), -1)
    if min(matrix.shape) < 3:
        raise ValueError("SVD representation requires at least three matrix dimensions")
    return np.linalg.svd(matrix, compute_uv=False)[:3]
