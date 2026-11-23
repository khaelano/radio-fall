"""Difference transforms that turn aligned amplitude into the sequence signal.

``squared_difference`` is the current representation: the notebook export, the
trained models and the Rust live detector all use ``log1p`` of it.
``absolute_difference`` is a variant that is not yet exported or trained.
``tone_mean_squared_log_ratio`` averages each receiver's relative changes over
its tones, removing the per-tone pattern that identifies a session
(``docs/reports/tone-pooling-2026-11-23.md``). All act on one segment at a time
and never difference across a gap. ``quiet_floor`` averages a signal over
still periods, for subtracting a session's per-tone idle level.
"""

from collections.abc import Iterable

import numpy as np


def squared_difference(values: np.ndarray) -> np.ndarray:
    """Square of adjacent sample changes in one segment, preserving NaN.

    Args:
        values: Samples in time order along the first axis.

    Returns:
        The same shape with NaN at the first sample and wherever either
        neighbour is missing.
    """
    result = np.full_like(values, np.nan)
    result[1:] = np.square(values[1:] - values[:-1])
    return result


def absolute_difference(values: np.ndarray) -> np.ndarray:
    """Magnitude of adjacent sample changes in one segment, preserving NaN.

    Variant of ``squared_difference`` without squaring: each change keeps its
    linear size instead of being weighted by itself, so large spikes do not
    dominate small movements.

    Args:
        values: Samples in time order along the first axis.

    Returns:
        The same shape with NaN at the first sample and wherever either
        neighbour is missing.
    """
    result = np.full_like(values, np.nan)
    result[1:] = np.abs(values[1:] - values[:-1])
    return result


def tone_mean_squared_log_ratio(values: np.ndarray) -> np.ndarray:
    """Mean over tones of the squared change in log amplitude, per receiver.

    Each tone contributes its relative change ``(ln a[t] - ln a[t - 1]) ** 2``,
    so tones that are loud only because of multipath do not dominate. Averaging
    over the tone axis keeps when and how much each receiver's signal moved and
    drops which tones responded.

    Args:
        values: Positive amplitudes ``[time, receiver, tone]`` of one segment;
            NaN marks missing samples.

    Returns:
        ``[time, receiver, 1]``: NaN at the first sample and wherever no tone
        of that receiver has a finite change.

    Raises:
        ValueError: If values are not three-dimensional or not positive.
    """
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 3:
        raise ValueError("Expected [time, receiver, tone] amplitudes")
    if np.any(array[np.isfinite(array)] <= 0):
        raise ValueError("Log ratios require positive amplitudes")
    change = squared_difference(np.log(array))
    finite = np.isfinite(change)
    count = finite.sum(axis=2, keepdims=True)
    total = np.where(finite, change, 0).sum(axis=2, keepdims=True)
    return np.divide(total, count, out=np.full(count.shape, np.nan), where=count > 0)


def quiet_floor(blocks: Iterable[np.ndarray]) -> np.ndarray:
    """Mean of each feature over the finite samples of still periods.

    Args:
        blocks: Arrays with time on axis zero and the same feature shape, such
            as ``[time, receiver, tone]``; NaN marks missing samples, which
            are skipped rather than filled.

    Returns:
        The per-feature mean; zero for a feature without any finite sample.

    Raises:
        ValueError: If no block is given.
    """
    total = count = None
    for block in blocks:
        values = np.asarray(block, dtype=np.float64)
        finite = np.isfinite(values)
        block_total = np.where(finite, values, 0).sum(axis=0)
        block_count = finite.sum(axis=0)
        total = block_total if total is None else total + block_total
        count = block_count if count is None else count + block_count
    if total is None:
        raise ValueError("Quiet floor requires at least one block")
    return np.divide(total, count, out=np.zeros_like(total), where=count > 0)
