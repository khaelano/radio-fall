"""Pure data preparation helpers for the live CSI viewer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ..acquisition.buffer import BufferSnapshot
from ..preprocessing.phase import (
    HE20_VALID_SUBCARRIERS,
    HT20_VALID_SUBCARRIERS,
    phase_change_from_baseline,
)


DASHBOARD_TRACE_COUNTS = (8, 12, 16)
DEFAULT_DASHBOARD_SUBCARRIERS = 12
DEFAULT_INSPECT_SUBCARRIER = 2
VALID_SUBCARRIERS = tuple(
    sorted(HT20_VALID_SUBCARRIERS | HE20_VALID_SUBCARRIERS)
)


class RenderGate:
    """Track whether each view needs a new numerical/render update."""

    def __init__(self, view_count: int = 2) -> None:
        if view_count < 1:
            raise ValueError("view_count must be positive")
        self._rendered: list[tuple[int | None, int]] = [
            (None, -1) for _ in range(view_count)
        ]

    def needs_render(
        self,
        view_index: int,
        sequence: int | None,
        config_version: int,
    ) -> bool:
        """Return whether a view is new or its controls became dirty."""

        previous_sequence, previous_config = self._rendered[view_index]
        return sequence != previous_sequence or config_version != previous_config

    def mark_rendered(
        self,
        view_index: int,
        sequence: int | None,
        config_version: int,
    ) -> None:
        """Record the sequence and configuration used by one view."""

        self._rendered[view_index] = (sequence, config_version)


@dataclass(frozen=True)
class PreparedCsiFrame:
    """Numerical arrays shared by the dashboard and detail renderers."""

    sequence: int | None
    timestamps: np.ndarray
    subcarriers: tuple[int, ...]
    amplitudes: np.ndarray
    raw_phases: np.ndarray
    calibrated_phases: np.ndarray
    selected_phases: np.ndarray
    mean_i: np.ndarray
    mean_q: np.ndarray
    rssi: np.ndarray
    noise_floor: np.ndarray

    @property
    def phases(self) -> np.ndarray:
        """Return phase values in the currently selected display mode."""

        return self.selected_phases


def as_matrix(rows: Any, *, width: int | None = None) -> np.ndarray:
    """Convert possibly ragged snapshot rows to a float32 matrix."""

    if rows is None or len(rows) == 0:
        return np.empty((0, 0 if width is None else width), dtype=np.float32)
    try:
        values = np.asarray(rows, dtype=np.float32)
        if values.ndim == 2 and (width is None or values.shape[1] == width):
            return values
    except ValueError:
        pass

    target_width = width if width is not None else max(len(row) for row in rows)
    result = np.full((len(rows), target_width), np.nan, dtype=np.float32)
    for index, row in enumerate(rows):
        result[index, : min(len(row), target_width)] = row[:target_width]
    return result


def mean_rows(values: np.ndarray) -> np.ndarray:
    """Return a NaN-safe mean for every row."""

    if values.ndim != 2:
        return np.empty(0, dtype=np.float32)
    valid = np.isfinite(values)
    counts = valid.sum(axis=1)
    totals = np.nansum(values, axis=1)
    return np.divide(
        totals,
        counts,
        out=np.full(totals.shape, np.nan, dtype=np.float32),
        where=counts > 0,
    )


def representative_subcarriers(
    count: int,
    available: tuple[int, ...] | list[int] | None = None,
) -> tuple[int, ...]:
    """Choose evenly spaced valid physical subcarriers.

    The selection is based on physical subcarrier order rather than the
    receiver's serialized slot order, so it remains symmetric around DC and
    stable when the requested trace count changes.
    """

    if count not in DASHBOARD_TRACE_COUNTS:
        raise ValueError(f"trace count must be one of {DASHBOARD_TRACE_COUNTS}")
    if available is None:
        candidates = VALID_SUBCARRIERS
    else:
        available_set = set(available)
        valid_layout = (
            HE20_VALID_SUBCARRIERS
            if any(abs(index) > 32 for index in available_set)
            else HT20_VALID_SUBCARRIERS
        )
        candidates = tuple(
            index for index in sorted(valid_layout) if index in available_set
        )
    if not candidates:
        return ()
    selected_count = min(count, len(candidates))
    positions = np.rint(
        np.linspace(0, len(candidates) - 1, selected_count)
    ).astype(int)
    return tuple(candidates[position] for position in positions)


def _ordered_phase_matrix(
    rows: Any,
    indices: tuple[int, ...],
) -> tuple[tuple[int, ...], np.ndarray]:
    """Return a phase matrix in ascending physical subcarrier order."""

    if not indices:
        return (), as_matrix(rows)
    order = np.argsort(np.asarray(indices, dtype=np.int32))
    matrix = as_matrix(rows, width=len(indices))
    return tuple(indices[index] for index in order), matrix[:, order]


def prepare_frame(
    snapshot: BufferSnapshot,
    *,
    phase_mode: str,
    phase_mode_change: str,
    phase_mode_raw: str,
    window_seconds: float,
) -> PreparedCsiFrame:
    """Prepare one full snapshot for both active renderers."""

    timestamps = np.asarray(snapshot.timestamps, dtype=np.float64)
    if timestamps.size:
        timestamps = timestamps - timestamps[-1]

    subcarriers, amplitudes = _ordered_phase_matrix(
        snapshot.phase_amplitudes,
        tuple(snapshot.phase_subcarriers),
    )
    _raw_indices, raw_phases = _ordered_phase_matrix(
        snapshot.raw_phases,
        tuple(snapshot.phase_subcarriers),
    )
    _calibrated_indices, calibrated_phases = _ordered_phase_matrix(
        snapshot.calibrated_phases,
        tuple(snapshot.phase_subcarriers),
    )
    if phase_mode == phase_mode_raw:
        selected_phases = raw_phases
    elif phase_mode == phase_mode_change:
        selected_phases = phase_change_from_baseline(
            calibrated_phases,
            timestamps,
            window_seconds=window_seconds,
        )
    else:
        selected_phases = calibrated_phases

    real = as_matrix(snapshot.real)
    imaginary = as_matrix(snapshot.imaginary)
    return PreparedCsiFrame(
        sequence=snapshot.end_sequence,
        timestamps=timestamps,
        subcarriers=subcarriers,
        amplitudes=amplitudes,
        raw_phases=raw_phases,
        calibrated_phases=calibrated_phases,
        selected_phases=selected_phases,
        mean_i=mean_rows(real),
        mean_q=mean_rows(imaginary),
        rssi=np.asarray(snapshot.rssi, dtype=np.float32),
        noise_floor=np.asarray(snapshot.noise_floor, dtype=np.float32),
    )


def phase_column(frame: PreparedCsiFrame, subcarrier: int) -> np.ndarray:
    """Return the selected phase column, or an empty array if unavailable."""

    try:
        column = frame.subcarriers.index(subcarrier)
    except ValueError:
        return np.empty(0, dtype=np.float32)
    return frame.selected_phases[:, column]
