"""Exploratory per-recording amplitude scaling and native time-window filtering."""

import numpy as np


def hampel_subcarriers(
    amplitude: np.ndarray,
    times: np.ndarray,
    *,
    window_seconds: float = 0.1,
    min_periods: int = 5,
    threshold: float = 5.0,
    parallel: bool = True,
    simd: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Replace temporal outliers independently in each subcarrier.

    Uses inclusive centered timestamp windows and finite samples only. A center
    is replaced when its distance exceeds threshold * 1.4826 * MAD and its
    window has enough samples and positive MAD. Windows read the original input.

    Args:
        amplitude: Matrix (packets, subcarriers), with NaN for invalid samples.
        times: Finite nondecreasing packet times in seconds; duplicates allowed.
        window_seconds: Positive full window duration.
        min_periods: Positive minimum finite count per subcarrier window.
        threshold: Nonnegative scaled MAD multiplier.
        parallel: Process subcarriers using Rayon workers.
        simd: Enable runtime AVX2 absolute deviations when supported.

    Returns:
        Filtered float64 matrix and boolean replacement mask; inputs unchanged.

    Raises:
        ValueError: Invalid shapes, parameters, infinite amplitudes or times.
        RuntimeError: The native extension needs to be built or updated.
    """
    try:
        from fall_detection._radio_native import hampel_filter
    except ImportError as exc:
        raise RuntimeError(
            "Build the Rust extension with 'uv sync --inexact --extra analysis "
            "--reinstall-package radio-fall-detection', then restart the kernel."
        ) from exc
    values = np.asarray(amplitude, dtype=np.float64)
    times = np.asarray(times, dtype=np.float64)
    if values.ndim != 2 or times.ndim != 1 or len(times) != values.shape[0]:
        raise ValueError(
            "Expected amplitude (packets, subcarriers) and times (packets,)"
        )
    filtered, replaced = hampel_filter(
        values.tobytes(order="F"),
        times.tobytes(),
        values.shape[1],
        window_seconds,
        min_periods,
        threshold,
        parallel,
        simd,
    )
    return (
        np.frombuffer(filtered, dtype=np.float64)
        .reshape(values.shape, order="F")
        .copy(),
        np.frombuffer(replaced, dtype=np.bool_).reshape(values.shape, order="F").copy(),
    )


def normalize_subcarriers(
    amplitude: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Scale each subcarrier to [-1, 1] over its entire recording.

    Args:
        amplitude: Matrix (packets, subcarriers), masked with NaN.

    Returns:
        Scaled matrix, per-column minima and maxima. Empty columns retain NaN;
        constant finite columns map to zero. Scaling uses future samples.
    """
    finite = np.isfinite(amplitude)
    has_data = finite.any(axis=0)
    lower = np.full(amplitude.shape[1], np.nan)
    upper = np.full(amplitude.shape[1], np.nan)
    lower[has_data] = np.min(
        np.where(finite[:, has_data], amplitude[:, has_data], np.inf), axis=0
    )
    upper[has_data] = np.max(
        np.where(finite[:, has_data], amplitude[:, has_data], -np.inf), axis=0
    )
    normalized = np.full(amplitude.shape, np.nan)
    varying = has_data & (upper > lower)
    normalized[:, varying] = (
        2 * (amplitude[:, varying] - lower[varying]) / (upper[varying] - lower[varying])
        - 1
    )
    constant = has_data & ~varying
    normalized[:, constant] = np.where(finite[:, constant], 0.0, np.nan)
    return np.clip(normalized, -1, 1), lower, upper
