"""Per-recording CSI quality measurements computed from the frame tables."""

from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

from ..radio.preprocessing.phase import DEFAULT_PHASE_AMPLITUDE_FLOOR, phase_slot_mask
from ._timeline import PHASES
from .session_frames import AnalysisSession

_COLUMNS = (
    "sequence",
    "rx_radio_us",
    "transmitter_mac",
    "sig_mode",
    "mcs",
    "bandwidth",
    "stbc",
    "first_word_invalid",
    "csi",
    "capture_time_ns",
)
_MODULUS = 2**32
_HALF_RANGE = 2**31
_CHUNK_ROWS = 2048
_READ_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    IndexError,
    RuntimeError,
    pa.ArrowException,
)


def _phase_counts(sensing: pa.Table) -> dict[str, int]:
    """Count rows by phase-mask support and usable subcarriers.

    Args:
        sensing: Sensing-link frames with ``csi``, ``stbc`` and
            ``first_word_invalid`` columns.

    Returns:
        Totals of supported, unreadable and unsupported rows plus the usable
        and maximum subcarrier sums of the supported rows.
    """
    totals = {
        "phase_mask_supported_rows": 0,
        "phase_mask_unreadable_rows": 0,
        "phase_mask_unsupported_rows": 0,
        "phase_usable_subcarriers_sum": 0,
        "phase_max_subcarriers_sum": 0,
    }
    for offset in range(0, sensing.num_rows, _CHUNK_ROWS):
        chunk = sensing.slice(offset, _CHUNK_ROWS)
        csi = chunk.column("csi").combine_chunks()
        keys = np.column_stack(
            (
                pc.binary_length(csi).to_numpy(zero_copy_only=False),
                chunk.column("stbc").to_numpy(zero_copy_only=False),
                chunk.column("first_word_invalid").to_numpy(zero_copy_only=False),
            )
        ).astype(np.int64)
        groups, inverse = np.unique(keys, axis=0, return_inverse=True)
        inverse = inverse.reshape(-1)
        # Each group shares one immutable physical-slot mask. Only the
        # amplitudes differ across packets, so evaluate a group with NumPy.
        for group, (declared, stbc, first_word) in enumerate(groups):
            rows = np.flatnonzero(inverse == group)
            if declared <= 0 or declared % 2:
                totals["phase_mask_unreadable_rows"] += len(rows)
                continue
            payload = b"".join(csi.take(pa.array(rows)).to_pylist())
            matrix = np.frombuffer(payload, dtype=np.int8).reshape(len(rows), declared)
            mask = phase_slot_mask(
                sig_mode=4,
                bandwidth=0,
                stbc=int(stbc),
                pair_count=int(declared) // 2,
                first_word_invalid=bool(first_word),
            )
            if not mask:
                totals["phase_mask_unsupported_rows"] += len(matrix)
                continue
            imaginary = matrix[:, 0::2].astype(np.float64)
            real = matrix[:, 1::2].astype(np.float64)
            amplitude = np.hypot(real, imaginary)
            usable = np.asarray(mask)[None, :] & (
                amplitude >= DEFAULT_PHASE_AMPLITUDE_FLOOR
            )
            totals["phase_mask_supported_rows"] += len(matrix)
            totals["phase_usable_subcarriers_sum"] += int(usable.sum())
            totals["phase_max_subcarriers_sum"] += int(sum(mask) * len(matrix))
    return totals


def _interval_metrics(
    sequences: np.ndarray, timestamps: np.ndarray, rate: float
) -> dict:
    sequence_deltas = np.diff(sequences) % _MODULUS
    forward = (sequence_deltas > 0) & (sequence_deltas < _HALF_RANGE)
    raw = np.diff(timestamps)
    wraps = raw < -_HALF_RANGE
    resets = (raw < 0) & ~wraps
    adjusted = np.where(wraps, raw + _MODULUS, raw)
    deltas = adjusted[adjusted > 0].astype(np.float64)
    elapsed = float(deltas.sum() / 1e6)
    period = 1e6 / rate
    gaps = deltas[deltas > 1.5 * period]
    return {
        "sequence_missing_frames": int((sequence_deltas[forward] - 1).sum()),
        "sequence_duplicates": int((sequence_deltas == 0).sum()),
        "sequence_out_of_order": int((sequence_deltas >= _HALF_RANGE).sum()),
        "timestamp_interval_count": len(deltas),
        "timestamp_elapsed_seconds": elapsed,
        "effective_sampling_rate_hz": len(deltas) / elapsed if elapsed else None,
        "median_interval_ms": float(np.median(deltas) / 1000) if len(deltas) else None,
        "p95_interval_ms": float(np.percentile(deltas, 95) / 1000)
        if len(deltas)
        else None,
        "max_interval_ms": float(deltas.max() / 1000) if len(deltas) else None,
        "timestamp_gap_intervals": len(gaps),
        "estimated_missing_from_timestamp_gaps": int(
            np.maximum(np.rint(gaps / period) - 1, 0).sum()
        ),
        "timestamp_wraps": int(wraps.sum()),
        "timestamp_resets": int(resets.sum()),
        "timestamp_duplicates": int((raw == 0).sum()),
    }


def _recording_frames(
    session: AnalysisSession, attempt_key: str, receiver_id: str
) -> pa.Table | None:
    """Read the frames of one recording in journal (delivery) order.

    Returns ``None`` when the frame tables hold no window for the attempt.
    """
    index = session.attempt_indices.get(attempt_key)
    if index is None:
        return None
    return pa.table(session.frames.attempt_frames(index, receiver_id, list(_COLUMNS)))


def scan_receiver(
    session: AnalysisSession,
    attempt_key: str,
    receiver_id: str,
    rate: float,
    intervals: dict,
) -> dict[str, Any]:
    """Measure one receiver recording without retaining CSI payloads.

    Frames are read in journal order, which is delivery order, so sequence
    ordering metrics describe the transport. Phase packet counts assign sensing
    frames to phases by capture time, the same clock as the analysis packets.

    Args:
        session: Analysis session holding the frame tables.
        attempt_key: Attempt identifier from ``session.attempts``.
        receiver_id: Receiver identifier such as ``"rx-1"``.
        rate: Nominal sampling rate in hertz.
        intervals: Phase name to ``(start_ns, stop_ns)`` host-clock intervals.

    Returns:
        A JSON-serializable mapping with ``metrics`` and ``phase_counts``.
        Read failures are reported in ``metrics["read_error"]``.
    """
    metrics: dict[str, Any] = {
        "has_frames": False,
        "raw_csi_rows": 0,
        "sensing_link_rows": 0,
        "phase_mask_supported_rows": 0,
        "phase_mask_unreadable_rows": 0,
        "phase_mask_unsupported_rows": 0,
        "phase_usable_subcarriers_sum": 0,
        "phase_max_subcarriers_sum": 0,
        "unassigned_phase_rows": 0,
        "read_error": "",
    }
    phase_counts = dict.fromkeys(PHASES, 0)
    sequences = timestamps = np.array([], dtype=np.int64)
    try:
        table = _recording_frames(session, attempt_key, receiver_id)
        rows = 0 if table is None else table.num_rows
        metrics["raw_csi_rows"] = rows
        metrics["has_frames"] = rows > 0
        if table is not None and rows:
            selected = pc.and_(
                pc.and_(
                    pc.equal(table.column("transmitter_mac"), session.transmitter_mac),
                    pc.equal(table.column("sig_mode"), 4),
                ),
                pc.and_(
                    pc.equal(table.column("mcs"), 0),
                    pc.equal(table.column("bandwidth"), 0),
                ),
            )
            sensing = table.filter(selected)
            metrics["sensing_link_rows"] = sensing.num_rows
            sequences = (
                sensing.column("sequence").to_numpy().astype(np.int64) % _MODULUS
            )
            timestamps = (
                sensing.column("rx_radio_us").to_numpy().astype(np.int64) % _MODULUS
            )
            metrics.update(_phase_counts(sensing))
            capture = sensing.column("capture_time_ns").to_numpy()
            for phase, (start, stop) in intervals.items():
                if phase in phase_counts and stop is not None and stop >= start:
                    phase_counts[phase] += int(
                        ((capture >= start) & (capture < stop)).sum()
                    )
    except _READ_ERRORS as exc:
        metrics["read_error"] = f"frames: {exc}"
    metrics.update(_interval_metrics(sequences, timestamps, rate))
    metrics["unassigned_phase_rows"] = metrics["sensing_link_rows"] - sum(
        phase_counts.values()
    )
    supported = metrics["phase_mask_supported_rows"]
    maximum = metrics["phase_max_subcarriers_sum"]
    metrics["phase_usable_subcarriers_mean"] = (
        metrics["phase_usable_subcarriers_sum"] / supported if supported else None
    )
    metrics["phase_usable_fraction"] = (
        metrics["phase_usable_subcarriers_sum"] / maximum if maximum else None
    )
    return {"metrics": metrics, "phase_counts": phase_counts}
