"""Bounded-memory CSV scans and vectorized CSI quality measurements."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..radio.preprocessing.phase import DEFAULT_PHASE_AMPLITUDE_FLOOR, phase_slot_mask
from ._timeline import PHASES

_CSI_COLUMNS = (
    "id",
    "mac",
    "sig_mode",
    "mcs",
    "bandwidth",
    "local_timestamp",
    "len",
    "stbc",
    "first_word",
    "data",
)
_TIMING_COLUMNS = ("sequence", "rx_radio_timestamp_us", "host_receive_monotonic_ns")
_MODULUS = 2**32
_HALF_RANGE = 2**31
_CHUNK_ROWS = 2048


def _phase_counts(frame: pd.DataFrame) -> dict[str, int]:
    totals = {
        "phase_mask_supported_rows": 0,
        "phase_mask_unreadable_rows": 0,
        "phase_mask_unsupported_rows": 0,
        "phase_usable_subcarriers_sum": 0,
        "phase_max_subcarriers_sum": 0,
    }
    # Each group shares one immutable physical-slot mask. Only the amplitudes
    # differ across packets, so evaluate the complete group with NumPy.
    for key, group in frame.groupby(["len", "stbc", "first_word"], dropna=False):
        if any(pd.isna(value) or value != int(value) for value in key):
            totals["phase_mask_unreadable_rows"] += len(group)
            continue
        declared, stbc, first_word = map(int, key)
        if declared < 0 or declared % 2:
            totals["phase_mask_unreadable_rows"] += len(group)
            continue
        decoded = []
        for payload in group["data"]:
            try:
                values = json.loads(payload)
                if not isinstance(values, list) or len(values) != declared:
                    raise ValueError("CSI length mismatch")
                decoded.append(values)
            except (TypeError, ValueError):
                totals["phase_mask_unreadable_rows"] += 1
        if not decoded:
            continue
        try:
            matrix = np.asarray(decoded, dtype=np.float64)
            if matrix.shape != (len(decoded), declared):
                raise ValueError("CSI is not a flat numeric vector")
        except (TypeError, ValueError):
            valid_rows = []
            for row in decoded:
                try:
                    values = np.asarray(row, dtype=np.float64)
                    if values.shape != (declared,):
                        raise ValueError("CSI is not a flat numeric vector")
                    valid_rows.append(values)
                except (TypeError, ValueError):
                    totals["phase_mask_unreadable_rows"] += 1
            if not valid_rows:
                continue
            matrix = np.stack(valid_rows)
        mask = phase_slot_mask(
            sig_mode=4,
            bandwidth=0,
            stbc=stbc,
            pair_count=declared // 2,
            first_word_invalid=bool(first_word),
        )
        if not mask:
            totals["phase_mask_unsupported_rows"] += len(matrix)
            continue
        imaginary, real = matrix[:, 0::2], matrix[:, 1::2]
        amplitude = np.hypot(real, imaginary)
        usable = (
            np.asarray(mask)[None, :]
            & np.isfinite(real)
            & np.isfinite(imaginary)
            & np.isfinite(amplitude)
            & (amplitude >= DEFAULT_PHASE_AMPLITUDE_FLOOR)
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


def scan_receiver(
    directory: Path, transmitter_mac: str, rate: float, intervals: dict
) -> dict[str, Any]:
    """Scan one receiver recording without retaining CSI payloads in the result."""
    csi_path, timing_path = directory / "csi.csv", directory / "radio_timing.csv"
    metrics = {
        "receiver_dir_exists": directory.is_dir(),
        "csi_file_exists": csi_path.is_file(),
        "timing_file_exists": timing_path.is_file(),
        "raw_csi_rows": 0,
        "timing_rows": 0,
        "sensing_link_rows": 0,
        "csi_timing_sequence_mismatches": 0,
        "csi_timing_timestamp_mismatches": 0,
        "malformed_sensing_metadata_rows": 0,
        "phase_mask_supported_rows": 0,
        "phase_mask_unreadable_rows": 0,
        "phase_mask_unsupported_rows": 0,
        "phase_usable_subcarriers_sum": 0,
        "phase_max_subcarriers_sum": 0,
        "unassigned_phase_rows": 0,
        "read_error": "",
    }
    phase_counts = dict.fromkeys(PHASES, 0)
    timing = pd.DataFrame(columns=_TIMING_COLUMNS)
    errors = []
    if timing_path.is_file():
        try:
            timing = pd.read_csv(
                timing_path,
                usecols=list(_TIMING_COLUMNS),
                dtype={"host_receive_monotonic_ns": "Int64"},
            )
            for name in _TIMING_COLUMNS[:2]:
                timing[name] = pd.to_numeric(timing[name], errors="coerce")
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            errors.append(f"radio_timing.csv: {exc}")
    metrics["timing_rows"] = len(timing)
    sequences, timestamps = [], []
    if csi_path.is_file():
        try:
            with pd.read_csv(
                csi_path,
                usecols=list(_CSI_COLUMNS),
                chunksize=_CHUNK_ROWS,
                dtype={"mac": str, "data": str},
                keep_default_na=False,
            ) as chunks:
                for chunk in chunks:
                    offset = metrics["raw_csi_rows"]
                    metrics["raw_csi_rows"] += len(chunk)
                    for name in _CSI_COLUMNS:
                        if name not in ("mac", "data"):
                            chunk[name] = pd.to_numeric(chunk[name], errors="coerce")
                    sensing = (
                        chunk["mac"].str.strip().str.lower().eq(transmitter_mac)
                        & chunk["sig_mode"].eq(4)
                        & chunk["mcs"].eq(0)
                        & chunk["bandwidth"].eq(0)
                    ).to_numpy()
                    filtered = chunk.loc[sensing]
                    metrics["sensing_link_rows"] += len(filtered)
                    ids = filtered["id"].to_numpy(dtype=np.float64)
                    ticks = filtered["local_timestamp"].to_numpy(dtype=np.float64)
                    valid = np.isfinite(ids) & np.isfinite(ticks)
                    valid &= (ids == np.floor(ids)) & (ticks == np.floor(ticks))
                    metrics["malformed_sensing_metadata_rows"] += int((~valid).sum())
                    sequences.append(ids[valid].astype(np.int64) % _MODULUS)
                    timestamps.append(ticks[valid].astype(np.int64) % _MODULUS)
                    for name, value in _phase_counts(filtered).items():
                        metrics[name] += value

                    paired = timing.iloc[offset : offset + len(chunk)]
                    count = len(paired)
                    if count:
                        id_match = (
                            chunk["id"].iloc[:count].to_numpy()
                            == paired["sequence"].to_numpy()
                        )
                        tick_match = (
                            chunk["local_timestamp"].iloc[:count].to_numpy()
                            == paired["rx_radio_timestamp_us"].to_numpy()
                        )
                        metrics["csi_timing_sequence_mismatches"] += int(
                            (~id_match).sum()
                        )
                        metrics["csi_timing_timestamp_mismatches"] += int(
                            (~tick_match).sum()
                        )
                        host = paired["host_receive_monotonic_ns"].to_numpy(
                            dtype=np.int64, na_value=-1
                        )
                        host = host[
                            sensing[:count] & id_match & tick_match & (host >= 0)
                        ]
                        for phase, (start, stop) in intervals.items():
                            if (
                                phase in phase_counts
                                and stop is not None
                                and stop >= start
                            ):
                                phase_counts[phase] += int(
                                    ((host >= start) & (host < stop)).sum()
                                )
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            errors.append(f"csi.csv: {exc}")
    seq = np.concatenate(sequences) if sequences else np.array([], dtype=np.int64)
    ticks = np.concatenate(timestamps) if timestamps else np.array([], dtype=np.int64)
    metrics.update(_interval_metrics(seq, ticks, rate))
    metrics["row_count_difference"] = metrics["raw_csi_rows"] - metrics["timing_rows"]
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
    metrics["read_error"] = "; ".join(errors)
    return {"metrics": metrics, "phase_counts": phase_counts}
