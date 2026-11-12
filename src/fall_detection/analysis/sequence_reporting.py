"""Bounded, cached display reads from memory-mapped sequence arrays."""

from functools import lru_cache
from pathlib import Path

import numpy as np

from .sequence_cache import fingerprint, read_segment, stamp


def _array_identity(path: str, key: str) -> dict:
    source = Path(path)
    stored_key = "valid" if key == "availability" else key
    file = source / f"{stored_key}.npy"
    return dict(path=str(file.resolve()), **stamp(file))


@lru_cache(maxsize=24)
def _preview_array(path: str, key: str, max_points: int, identity: str) -> np.ndarray:
    """Copy a bounded display sample; never retain the full decoded recording."""
    with read_segment(path) as data:
        values = data["valid" if key == "availability" else key]
        if key in {"subcarriers", "receivers"}:
            preview = np.array(values, copy=True)
        elif key == "availability":
            available = values.any(axis=2).astype(np.float32)
            edges = np.linspace(
                0, len(values), min(max_points, len(values)) + 1, dtype=int
            )
            preview = (
                np.add.reduceat(available, edges[:-1], axis=0) / np.diff(edges)[:, None]
            )
        else:
            indices = np.linspace(
                0, len(values) - 1, min(max_points, len(values)), dtype=int
            )
            preview = np.array(values[indices], copy=True)
    preview.setflags(write=False)
    return preview


def preview_array(path: str, key: str, max_points: int) -> np.ndarray:
    """Return a bounded display sample, invalidated when its source changes."""
    if max_points < 2:
        raise ValueError("max_points must be at least two")
    return _preview_array(
        path, key, max_points, fingerprint(_array_identity(path, key))
    )
