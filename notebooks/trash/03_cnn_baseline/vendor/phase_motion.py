"""Snapshot of the canonical signed circular change calculation."""

import numpy as np


def phase_change_matrix(
    values: np.ndarray,
    seconds: np.ndarray,
    lag_seconds: float,
    *,
    phase_codes: np.ndarray | None = None,
) -> np.ndarray:
    """Keep the signed circular change of every supplied subcarrier separately.

    Select the packet at or just before ``t - lag_seconds`` without resampling.
    Actual lag must not exceed 1.5 times the requested lag. No absolute value,
    subcarrier reduction, temporal filter, or interpolation is applied.

    Args:
        values: Masked phase matrix, shape (packets, subcarriers).
        seconds: Finite nondecreasing packet times in seconds.
        lag_seconds: Positive requested lag; changes are radians per lag.
        phase_codes: Optional integer code per packet. Negative means outside
            the analyzed phases. When supplied, both lag endpoints must have
            the same nonnegative code.

    Returns:
        A matrix matching values, containing signed changes in [-pi, pi].
        Missing endpoints affect only their own subcarrier. Unsupported lags
        and excluded phase transitions remain all-NaN rows.

    Raises:
        ValueError: Shapes, times, lag, or phase codes are invalid.
    """
    values, seconds = np.asarray(values), np.asarray(seconds)
    if values.ndim != 2 or seconds.ndim != 1 or len(values) != len(seconds):
        raise ValueError("Expected a phase matrix and matching one-dimensional times")
    if not np.isfinite(lag_seconds) or lag_seconds <= 0:
        raise ValueError("lag_seconds must be finite and positive")
    if not np.isfinite(seconds).all() or np.any(np.diff(seconds) < 0):
        raise ValueError("Packet times must be finite and nondecreasing")
    previous = np.searchsorted(seconds, seconds - lag_seconds, side="right") - 1
    current = np.flatnonzero(previous >= 0)
    current = current[
        (seconds[current] - seconds[previous[current]]) <= 1.5 * lag_seconds
    ]
    if phase_codes is not None:
        phase_codes = np.asarray(phase_codes)
        if phase_codes.shape != seconds.shape or not np.issubdtype(
            phase_codes.dtype, np.integer
        ):
            raise ValueError("phase_codes must be matching one-dimensional integers")
        current = current[
            (phase_codes[current] >= 0)
            & (phase_codes[current] == phase_codes[previous[current]])
        ]
    changes = np.full(values.shape, np.nan)
    changes[current] = np.angle(
        np.exp(1j * (values[current] - values[previous[current]]))
    )
    return changes
