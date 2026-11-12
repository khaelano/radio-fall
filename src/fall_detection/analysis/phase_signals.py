"""Load a single receiver's physical CSI phase matrices for exploratory plots."""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ..radio.preprocessing.phase import decode_ltf_blocks


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
    session_dir: str | Path, attempt_id: str, receiver_id: str
) -> pd.DataFrame:
    """Load all CSI rows with validated timing and recording identifiers.

    Uses the canonical LTF decoder and its amplitude/physical-slot masks.
    Gateway captures require their validated mapped capture-time sidecar;
    delivery time is never substituted for sensing time.

    Args:
        session_dir: Schema-2 session directory.
        attempt_id: Trial/attempt identifier such as ``"001/01"``.
        receiver_id: Receiver directory identifier such as ``"rx-1"``.

    Returns:
        Packet rows, including non-sensing packets, on the host event clock.
        Raw CSV payloads and flags remain unchanged. Capture time is distinct
        from delivery time; ``time_source`` identifies the gateway clock mapping.

    Raises:
        ValueError: Identity, CSV alignment, payload, or timeline is invalid,
            or no supported sensing-link packets remain.
        FileNotFoundError: The requested attempt/receiver files are missing.
    """
    root = Path(session_dir)
    manifest = json.loads((root / "session.json").read_text(encoding="utf-8"))
    if manifest.get("artifact_schema_version") != 2:
        raise ValueError("Phase analysis requires a schema-2 session")
    if receiver_id in (".", "..") or Path(receiver_id).name != receiver_id:
        raise ValueError("receiver_id must be a receiver directory name")
    try:
        ordinal, number = map(int, attempt_id.split("/"))
    except ValueError as exc:
        raise ValueError("attempt_id must look like '001/01'") from exc
    matches = []
    for path in root.glob(f"trials/*/attempt_{number:02d}/attempt.json"):
        attempt = json.loads(path.read_text(encoding="utf-8"))
        if int(attempt["trial_ordinal"]) == ordinal:
            matches.append((path.parent, attempt))
    if len(matches) != 1:
        raise FileNotFoundError(
            f"Expected one attempt {attempt_id}; found {len(matches)}"
        )
    directory, attempt = matches[0]
    receiver = directory / "receivers" / receiver_id
    csi = pd.read_csv(receiver / "csi.csv")
    timing = pd.read_csv(receiver / "radio_timing.csv")
    csi["source_row"] = np.arange(len(csi), dtype=np.int64)
    if len(csi) != len(timing) or not np.array_equal(csi["id"], timing["sequence"]):
        raise ValueError("CSI and radio timing rows do not align by sequence")
    if not np.array_equal(csi["local_timestamp"], timing["rx_radio_timestamp_us"]):
        raise ValueError("CSI and radio timing receiver timestamps do not align")
    if csi.empty:
        return csi
    gateway_path = receiver / "gateway_timing.jsonl"
    if not gateway_path.is_file():
        raise ValueError("Gateway capture requires its capture-time sidecar")
    gateway = pd.read_json(gateway_path, lines=True, dtype={"run_id": str})
    if (
        len(gateway) != len(timing)
        or not gateway["schema_version"].eq(1).all()
        or not np.array_equal(gateway["sequence"], timing["sequence"])
        or not np.array_equal(
            gateway["rx_radio_timestamp_us"], timing["rx_radio_timestamp_us"]
        )
    ):
        raise ValueError("Gateway timing sidecar does not align with CSI")
    if (
        gateway["run_id"].nunique() != 1
        or gateway["transmitter_boot_id"].nunique() != 1
    ):
        raise ValueError("Gateway attempt mixes transmitter epochs")
    timing["capture_host_monotonic_ns"] = gateway["capture_host_monotonic_ns"]
    timing["capture_clock_uncertainty_us"] = gateway["clock_uncertainty_us"]
    for name in ("run_id", "transmitter_boot_id", "receiver_boot_id"):
        if name in gateway:
            timing[name] = gateway[name].astype(str)
    # Transport delivery can reorder records. Sort derived views only.
    order = timing["capture_host_monotonic_ns"].sort_values(kind="stable").index
    csi, timing = csi.loc[order], timing.loc[order]
    environment = manifest.get("environment", {})
    transmitter = (
        environment.get("radio_inventory", {})
        .get("transmitter", {})
        .get("mac", "")
        .lower()
    )
    if not transmitter:
        raise ValueError("Session radio inventory must specify a transmitter MAC")
    origin = int(attempt["started_monotonic_ns"])
    times, time_source = _event_times(timing, origin)
    rate = environment.get("nominal_rate_hz") or environment.get(
        "radio_profile", {}
    ).get("nominal_rate_hz")
    if rate is None or float(rate) <= 0:
        raise ValueError("A positive nominal sampling rate is required")
    packets = csi.reset_index(drop=True).copy()
    for name in timing:
        if name not in packets:
            packets[name] = timing[name].to_numpy()
    packets["capture_time_ns"] = timing["capture_host_monotonic_ns"].to_numpy(
        dtype=np.int64
    )
    packets["time_seconds"] = times
    packets["time_source"] = time_source
    packets["clock_uncertainty_us"] = timing["capture_clock_uncertainty_us"].to_numpy()
    packets["attempt_id"] = attempt_id
    packets["receiver_id"] = receiver_id
    packets["attempt_started_monotonic_ns"] = origin
    packets["attempt_ended_monotonic_ns"] = int(attempt["ended_monotonic_ns"])
    packets["nominal_rate_hz"] = float(rate)
    packets["is_sensing"] = (
        packets["type"].eq("CSI_DATA")
        & packets["mac"].str.lower().eq(transmitter)
        & packets["sig_mode"].eq(4)
        & packets["mcs"].eq(0)
        & packets["bandwidth"].eq(0)
    )
    return packets


def load_phase_signal(
    session_dir: str | Path, attempt_id: str, receiver_id: str
) -> PhaseSignal:
    """Load and calibrate sensing-link CSI using validated capture timing.

    Args:
        session_dir: Schema-2 raw session directory.
        attempt_id: Trial/attempt identifier such as ``001/01``.
        receiver_id: Receiver directory identifier such as ``rx-1``.

    Returns:
        Canonically decoded phase matrices on the recorded event timeline.
    """
    return phase_signal_from_packets(
        load_capture_packets(session_dir, attempt_id, receiver_id)
    )


def phase_signal_from_packets(packets: pd.DataFrame) -> PhaseSignal:
    """Decode one attempt/receiver packet DataFrame without reading raw files.

    Args:
        packets: Rows from ``load_capture_packets`` or the session Parquet
            export. I/Q arrays retain raw slot order and invalid-slot flags.

    Returns:
        Sensing-link matrices using the same masks and calibration as CSV input.

    Raises:
        ValueError: Multiple recordings, invalid payloads, or no sensing rows.
    """
    if packets.empty or any(
        packets[name].nunique(dropna=False) != 1
        for name in ("attempt_id", "receiver_id", "attempt_started_monotonic_ns")
    ):
        raise ValueError("Expected one nonempty attempt/receiver recording")
    csi = packets.loc[packets["is_sensing"]]
    first = packets.iloc[0]
    attempt_id, receiver_id = first["attempt_id"], first["receiver_id"]
    origin = int(first["attempt_started_monotonic_ns"])
    if csi.empty:
        raise ValueError(f"No sensing-link CSI in {attempt_id}/{receiver_id}")
    times = csi["time_seconds"].to_numpy(dtype=float)
    time_source = str(first["time_source"])
    bounds = pd.to_numeric(csi["clock_uncertainty_us"], errors="coerce")
    uncertainty = float(bounds.max()) if bounds.notna().all() else None
    return _decode_phase_rows(csi, times, origin, first, uncertainty, time_source)


def _decode_phase_rows(csi, times, origin, first, uncertainty, time_source):
    attempt_id, receiver_id = first["attempt_id"], first["receiver_id"]
    values, raw, calibrated, slopes, offsets, retained = [], [], [], [], [], []
    subcarriers = None
    skipped = 0
    for position, row in enumerate(csi.itertuples(index=False)):
        if hasattr(row, "data"):
            payload = np.asarray(json.loads(row.data), dtype=np.float64)
        else:
            payload = np.column_stack((row.csi_q, row.csi_i)).ravel()
        if payload.ndim != 1 or payload.size != int(row.len) or payload.size % 2:
            raise ValueError(f"Invalid CSI payload length in packet {row.id}")
        complex_values = payload[1::2] + 1j * payload[0::2]
        blocks = decode_ltf_blocks(
            complex_values,
            sig_mode=int(row.sig_mode),
            bandwidth=int(row.bandwidth),
            stbc=int(row.stbc),
            first_word_invalid=bool(row.first_word),
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


def _event_times(timing, origin_ns):
    captured = pd.to_numeric(
        timing["capture_host_monotonic_ns"], errors="coerce"
    ).to_numpy()
    if not np.isfinite(captured).all():
        raise ValueError("Gateway capture clock alignment is unavailable")
    return (captured - origin_ns) / 1e9, "gateway capture clock mapping"
