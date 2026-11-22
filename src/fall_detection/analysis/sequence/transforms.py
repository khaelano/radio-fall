"""Difference transforms that turn aligned amplitude into the sequence signal.

``squared_difference`` is the current representation: the notebook export, the
trained models and the Rust live detector all use ``log1p`` of it.
``absolute_difference`` is a variant that is not yet exported or trained.
Both act on one segment at a time and never difference across a gap.
"""

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
