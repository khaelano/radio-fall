"""Decode a single receiver's physical CSI phase matrices for exploratory plots."""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import polars as pl

from ..radio.preprocessing.phase import decode_ltf_blocks
from ._timeline import as_polars
from .session_frames import AnalysisSession

if TYPE_CHECKING:
    import pandas as pd

_ATTEMPT_ID = re.compile(r"\d+/\d+")


@dataclass(frozen=True)
class PhaseSignal:
    """One attempt on an event-aligned timeline, with signed physical subcarriers.

    Matrices have shape ``(packets, subcarriers)``. Raw phase retains packet
    offset and slope but masks unusable values using the production decoder.
    ``removed_offset`` is the fitted unwrapped intercept, in radians; compare
    it modulo 2*pi when plotting. No temporal filtering/resampling is applied.
    """

    attempt_id: str
    receiver_id: str
    time_seconds: np.ndarray
    subcarriers: np.ndarray
    complex_csi: np.ndarray
    raw_phase: np.ndarray
    calibrated_phase: np.ndarray
    removed_slope: np.ndarray
    removed_offset: np.ndarray
    started_monotonic_ns: int
    ended_monotonic_ns: int
    nominal_rate_hz: float
    time_source: str
    sync_uncertainty_us: float | None
    skipped_layout_rows: int


def load_capture_packets(
    session: AnalysisSession, attempt_id: str, receiver_id: str
) -> pl.DataFrame:
    """Load all CSI rows of one recording with validated timing and identifiers.

    Packets come from the converted frame tables and are sorted by capture
    time. Delivery time is never substituted for sensing time.

    Args:
        session: Analysis session built from the converted frame tables.
        attempt_id: Trial/attempt identifier such as ``"001/01"``.
        receiver_id: Receiver identifier such as ``"rx-1"``.

    Returns:
        Packet rows, including non-sensing packets, on the host event clock.
        Capture time is distinct from delivery time; ``time_source``
        identifies the gateway clock mapping.

    Raises:
        ValueError: ``attempt_id`` is malformed, the recording mixes transmitter
            epochs, or the session lacks a transmitter MAC or sampling rate.
        FileNotFoundError: The attempt or receiver is not part of the session.
    """
    if not _ATTEMPT_ID.fullmatch(attempt_id):
        raise ValueError("attempt_id must look like '001/01'")
    matches = as_polars(session.attempts).filter(pl.col("attempt_id") == attempt_id)
    if matches.height != 1:
        raise FileNotFoundError(
            f"Expected one attempt {attempt_id}; found {matches.height}"
        )
    attempt = matches.row(0, named=True)
    if receiver_id not in attempt["receiver_ids"]:
        raise FileNotFoundError(
            f"Attempt {attempt_id} has no frames from receiver {receiver_id}"
        )
    return pl.DataFrame(session.packets(attempt["attempt_key"], receiver_id))


def load_phase_signal(
    session: AnalysisSession, attempt_id: str, receiver_id: str
) -> PhaseSignal:
    """Load and calibrate sensing-link CSI using validated capture timing.

    Args:
        session: Analysis session built from the converted frame tables.
        attempt_id: Trial/attempt identifier such as ``001/01``.
        receiver_id: Receiver identifier such as ``rx-1``.

    Returns:
        Canonically decoded phase matrices on the recorded event timeline.
    """
    return phase_signal_from_packets(
        load_capture_packets(session, attempt_id, receiver_id)
    )


def phase_signal_from_packets(packets: "pl.DataFrame | pd.DataFrame") -> PhaseSignal:
    """Decode one attempt/receiver packet DataFrame without reading raw files.

    Args:
        packets: Rows from ``load_capture_packets`` (polars) or
            ``AnalysisSession.read_packets`` (pandas, converted on entry). I/Q
            arrays retain raw slot order and invalid-slot flags.

    Returns:
        Sensing-link matrices decoded with the canonical masks and calibration.

    Raises:
        ValueError: Multiple recordings, invalid payloads, or no sensing rows.
    """
    packets = as_polars(packets)
    if packets.is_empty() or any(
        packets[name].n_unique() != 1
        for name in ("attempt_id", "receiver_id", "attempt_started_monotonic_ns")
    ):
        raise ValueError("Expected one nonempty attempt/receiver recording")
    csi = packets.filter(pl.col("is_sensing"))
    first = packets.row(0, named=True)
    attempt_id, receiver_id = first["attempt_id"], first["receiver_id"]
    origin = int(first["attempt_started_monotonic_ns"])
    if csi.is_empty():
        raise ValueError(f"No sensing-link CSI in {attempt_id}/{receiver_id}")
    times = csi["time_seconds"].cast(pl.Float64).to_numpy()
    time_source = str(first["time_source"])
    bounds = csi["clock_uncertainty_us"].cast(pl.Float64, strict=False)
    known = bounds.is_not_null() & bounds.is_not_nan()
    uncertainty = float(bounds.max()) if known.all() else None
    return _decode_phase_rows(csi, times, origin, first, uncertainty, time_source)


def _decode_phase_rows(csi, times, origin, first, uncertainty, time_source):
    attempt_id, receiver_id = first["attempt_id"], first["receiver_id"]
    values, raw, calibrated, slopes, offsets, retained = [], [], [], [], [], []
    subcarriers = None
    skipped = 0
    columns = ("len", "sig_mode", "bandwidth", "stbc", "first_word", "csi_q", "csi_i")
    # The packet identifier is optional; it only labels payload errors.
    labels = ["id"] if "id" in csi.columns else []
    rows = csi.select(*labels, *columns).iter_rows(named=True)
    for position, row in enumerate(rows):
        quadrature = np.asarray(row["csi_q"], dtype=np.int16)
        in_phase = np.asarray(row["csi_i"], dtype=np.int16)
        payload = np.column_stack((quadrature, in_phase)).ravel()
        if payload.ndim != 1 or payload.size != int(row["len"]) or payload.size % 2:
            raise ValueError(
                f"Invalid CSI payload length in packet {row.get('id', position)}"
            )
        complex_values = payload[1::2] + 1j * payload[0::2]
        blocks = decode_ltf_blocks(
            complex_values,
            sig_mode=int(row["sig_mode"]),
            bandwidth=int(row["bandwidth"]),
            stbc=int(row["stbc"]),
            first_word_invalid=bool(row["first_word"]),
        )
        block = next((block for block in blocks if block.name == "HE-LTF"), None)
        if block is None:
            skipped += 1
            continue
        indices = np.asarray(block.subcarrier_indices)
        axis = np.arange(min(block.valid_subcarriers), max(block.valid_subcarriers) + 1)
        if subcarriers is None:
            subcarriers = axis
        elif not np.array_equal(subcarriers, axis):
            raise ValueError("Mixed physical subcarrier layouts within one attempt")
        keep = (indices >= axis[0]) & (indices <= axis[-1])
        target = indices[keep] - axis[0]
        raw_row = np.full(len(axis), np.nan)
        calibrated_row = np.full(len(axis), np.nan)
        complex_row = np.full(len(axis), np.nan + 1j * np.nan)
        raw_row[target] = np.asarray(block.raw_phases)[keep]
        calibrated_row[target] = np.asarray(block.calibrated_phases)[keep]
        complex_row[target] = np.asarray(block.csi)[keep]
        slope, offset = _phase_trend(raw_row, complex_row, axis)
        values.append(complex_row)
        raw.append(raw_row)
        calibrated.append(calibrated_row)
        slopes.append(slope)
        offsets.append(offset)
        retained.append(position)
    if not retained:
        raise ValueError(f"No supported HE-LTF packets in {attempt_id}/{receiver_id}")
    times = times[retained]
    if np.any(np.diff(times) < 0):
        raise ValueError(
            "Mapped packet times run backwards; inspect clock/timing integrity"
        )
    return PhaseSignal(
        attempt_id,
        receiver_id,
        times,
        subcarriers,
        np.asarray(values),
        np.asarray(raw),
        np.asarray(calibrated),
        np.asarray(slopes),
        np.asarray(offsets),
        origin,
        int(first["attempt_ended_monotonic_ns"]),
        float(first["nominal_rate_hz"]),
        time_source,
        uncertainty,
        skipped,
    )


def _phase_trend(raw, values, indices):
    valid = np.isfinite(raw)
    if valid.sum() < 3:
        return np.nan, np.nan
    x = indices[valid].astype(float)
    y = np.unwrap(raw[valid])
    weights = np.abs(values[valid])
    mean_x = np.average(x, weights=weights)
    mean_y = np.average(y, weights=weights)
    slope = np.sum(weights * (x - mean_x) * (y - mean_y)) / np.sum(
        weights * (x - mean_x) ** 2
    )
    return float(slope), float(mean_y - slope * mean_x)
