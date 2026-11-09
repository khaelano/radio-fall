"""Exploratory fixed-rate windows derived from amplitude recordings."""

import json
from pathlib import Path

import numpy as np

from .amplitude_pipeline import save_recording


def resample_amplitude(times: np.ndarray, amplitude: np.ndarray, valid: np.ndarray,
                       grid: np.ndarray, max_gap_seconds: float = 0.025
                       ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Linearly resample using valid adjacent samples and bounded gaps.

    Returns values, validity and left/right source indices. Duplicate timestamps
    must already have been resolved by the caller.
    """
    times, grid = np.asarray(times, dtype=float), np.asarray(grid, dtype=float)
    amplitude, valid = np.asarray(amplitude), np.asarray(valid, dtype=bool)
    if (times.ndim != 1 or not len(times) or amplitude.ndim != 2
            or amplitude.shape != valid.shape or len(times) != len(amplitude)
            or grid.ndim != 1 or not np.isfinite(times).all()
            or not np.isfinite(grid).all() or np.any(np.diff(times) <= 0)
            or not np.isfinite(max_gap_seconds) or max_gap_seconds <= 0):
        raise ValueError("Invalid resampling inputs")
    right = np.minimum(np.searchsorted(times, grid, side="left"), len(times) - 1)
    exact = times[right] == grid
    left = np.maximum(right - 1, 0)
    left[exact] = right[exact]
    gaps = times[right] - times[left]
    supported = exact | ((grid >= times[0]) & (grid <= times[-1]) & (right > 0)
                         & (gaps <= max_gap_seconds))
    mask = (supported[:, None] & valid[left] & valid[right]
            & np.isfinite(amplitude[left]) & np.isfinite(amplitude[right]))
    fraction = np.divide(grid - times[left], gaps, out=np.zeros_like(grid), where=gaps > 0)
    values = amplitude[left] + fraction[:, None] * (amplitude[right] - amplitude[left])
    values[~mask] = np.nan
    return values, mask, left, right


def generate_windows(
    input_dir: str | Path,
    output_dir: str | Path,
    *,
    durations: tuple[int, ...] = (2, 4, 6),
    rate_hz: int = 80,
    max_gap_seconds: float = 0.025,
    recording_paths: list[str] | None = None,
) -> dict[int, int]:
    """Create overlapping fixed-rate windows from each saved receiver recording.

    Linear interpolation uses only adjacent finite samples separated by at most
    max_gap_seconds. Missing support stays NaN and has a false validity mask.
    Windows use a half-window stride and must fit within the capture time range.
    The label is the phase at the window center; per-sample labels are retained.

    Args:
        input_dir: Derived per-recording NPZ directory.
        output_dir: Directory for duration-specific derived datasets.
        durations: Positive even durations in seconds.
        rate_hz: Positive output sample rate.
        max_gap_seconds: Largest allowed interpolation gap.
        recording_paths: Optional explicit selected recording paths.

    Returns:
        Number of windows written for each duration.
    """
    input_dir, output_dir = Path(input_dir).resolve(), Path(output_dir).resolve()
    if output_dir == input_dir or input_dir in output_dir.parents:
        raise ValueError("Window output must be separate from source recordings")
    if rate_hz <= 0 or max_gap_seconds <= 0 or any(d <= 0 or d % 2 for d in durations):
        raise ValueError("Expected positive rate, gap, and even window durations")
    counts = {duration: 0 for duration in durations}
    paths = (sorted(Path(path).resolve() for path in recording_paths)
             if recording_paths is not None else sorted(input_dir.rglob("*.npz")))
    if not paths:
        raise ValueError("No preprocessed recordings found")
    if any(not path.is_relative_to(input_dir) for path in paths):
        raise ValueError("Recording path is outside the source directory")
    for path in paths:
        with np.load(path, allow_pickle=False) as data:
            times = data["time_seconds"]
            amplitude = data["amplitude"]
            valid = data["valid"]
            phase = data["phase"]
            provenance = json.loads(str(data["provenance_json"]))
            subcarriers = data["subcarriers"]
            replaced = data["hampel_replaced"]
        if len(times) < 2 or not np.isfinite(times).all() or np.any(np.diff(times) < 0):
            raise ValueError(f"Invalid timestamps in {path}")
        # Duplicates select the last packet deterministically.
        indices = np.r_[np.diff(times) != 0, True]
        times, amplitude, valid, phase, replaced = (
            item[indices] for item in (times, amplitude, valid, phase, replaced)
        )
        first_tick = int(np.ceil(times[0] * rate_hz))
        last_tick = int(np.floor(times[-1] * rate_hz))
        grid = np.arange(first_tick, last_tick + 1) / rate_hz
        values, mask, left, right = resample_amplitude(times, amplitude, valid, grid, max_gap_seconds)
        exact = times[right] == grid
        supported = exact | ((grid >= times[0]) & (grid <= times[-1]) & (right > 0)
                             & (times[right] - times[left] <= max_gap_seconds))
        phase_grid = np.asarray(phase[left], dtype=object)
        phase_grid[~supported] = "unknown"
        replacement_mask = mask & (replaced[left] | replaced[right])
        for duration in durations:
            size = duration * rate_hz
            stride = size // 2
            initial = (-first_tick) % stride
            starts = np.arange(initial, max(initial, len(grid) - size + 1), stride)
            if not len(starts):
                continue
            window_indices = starts[:, None] + np.arange(size)
            target = output_dir / f"{duration}s" / path.relative_to(input_dir)
            info = dict(provenance, window_seconds=duration, sample_rate_hz=rate_hz,
                        stride_seconds=duration / 2, max_interpolation_gap_seconds=max_gap_seconds,
                        interpolation="linear", window_label="center_phase")
            save_recording(target, {
                "amplitude": values[window_indices].astype(np.float32),
                "valid": mask[window_indices],
                "hampel_replaced": replacement_mask[window_indices],
                "time_seconds": grid[window_indices],
                "phase": np.asarray(phase_grid[window_indices], dtype=str),
                "label": np.asarray(phase_grid[starts + size // 2], dtype=str),
                "subcarriers": subcarriers,
                "provenance_json": np.asarray(json.dumps(info)),
            })
            counts[duration] += len(starts)
    return counts
