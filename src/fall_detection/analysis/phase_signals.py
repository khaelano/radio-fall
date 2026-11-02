"""Load a single receiver's physical CSI phase matrices for exploratory plots."""

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..radio.acquisition.clock_sync import ClockSyncEstimator, ClockSyncSample
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


def load_phase_signal(
    session_dir: str | Path, attempt_id: str, receiver_id: str
) -> PhaseSignal:
    """Load and calibrate sensing-link CSI for one attempt and receiver.

    Uses the canonical LTF decoder and its amplitude/physical-slot masks.
    BLE captures use their validated mapped enqueue-time sidecar. USB receiver
    callbacks use the recorded affine fit; unavailable USB sync falls back to
    host receive timestamps, explicitly identified by ``time_source``. BLE
    captures never silently substitute delivery time for sensing time.

    Args:
        session_dir: Schema-2 session directory.
        attempt_id: Trial/attempt identifier such as ``"001/01"``.
        receiver_id: Receiver directory identifier such as ``"rx-1"``.

    Returns:
        Phase matrices in ascending physical subcarrier order and seconds
        relative to the attempt's recorded start.

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
    if len(csi) != len(timing) or not np.array_equal(csi["id"], timing["sequence"]):
        raise ValueError("CSI and radio timing rows do not align by sequence")
    if not np.array_equal(csi["local_timestamp"], timing["rx_radio_timestamp_us"]):
        raise ValueError("CSI and radio timing receiver timestamps do not align")
    ble_path = receiver / "gateway_timing.jsonl"
    if not ble_path.is_file():
        ble_path = receiver / "ble_timing.jsonl"
    if ble_path.is_file():
        ble = pd.read_json(ble_path, lines=True)
        if (
            len(ble) != len(timing)
            or not ble["schema_version"].eq(1).all()
            or not np.array_equal(ble["sequence"], timing["sequence"])
            or not np.array_equal(
                ble["rx_radio_timestamp_us"], timing["rx_radio_timestamp_us"]
            )
        ):
            raise ValueError("BLE timing sidecar does not align with CSI")
        if ble["run_id"].nunique() != 1 or ble["transmitter_boot_id"].nunique() != 1:
            raise ValueError("BLE attempt mixes transmitter epochs")
        timing["capture_host_monotonic_ns"] = ble["capture_host_monotonic_ns"]
        timing["capture_clock_uncertainty_us"] = ble["clock_uncertainty_us"]
        # Transport delivery can reorder records. Sort derived views only.
        order = timing["capture_host_monotonic_ns"].sort_values(kind="stable").index
        csi, timing = csi.loc[order], timing.loc[order]
    elif manifest.get("environment", {}).get("transport") in {"ble", "espnow_gateway"}:
        raise ValueError("BLE capture requires its capture-time sidecar")
    environment = manifest.get("environment", {})
    transmitter = (
        environment.get("radio_inventory", {})
        .get("transmitter", {})
        .get("mac", "")
        .lower()
    )
    if not transmitter:
        raise ValueError("Session radio inventory must specify a transmitter MAC")
    selected = (
        csi["type"].eq("CSI_DATA")
        & csi["mac"].str.lower().eq(transmitter)
        & csi["sig_mode"].eq(4)
        & csi["mcs"].eq(0)
        & csi["bandwidth"].eq(0)
    )
    csi, timing = csi.loc[selected], timing.loc[selected]
    if csi.empty:
        raise ValueError(f"No sensing-link CSI in {attempt_id}/{receiver_id}")
    origin = int(attempt["started_monotonic_ns"])
    times, time_source, uncertainty = _event_times(
        timing, receiver / "usb_clock_sync.csv", origin
    )
    values, raw, calibrated, slopes, offsets, retained = [], [], [], [], [], []
    subcarriers = None
    skipped = 0
    for position, row in enumerate(csi.itertuples(index=False)):
        payload = np.asarray(json.loads(row.data), dtype=np.float64)
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
    rate = environment.get("nominal_rate_hz") or environment.get(
        "radio_profile", {}
    ).get("nominal_rate_hz")
    if rate is None or float(rate) <= 0:
        raise ValueError("A positive nominal sampling rate is required")
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
        int(attempt["ended_monotonic_ns"]),
        float(rate),
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


def _event_times(timing, sync_path, origin_ns):
    if "capture_host_monotonic_ns" in timing:
        captured = pd.to_numeric(
            timing["capture_host_monotonic_ns"], errors="coerce"
        ).to_numpy()
        if not np.isfinite(captured).all():
            raise ValueError("BLE capture clock alignment is unavailable")
        uncertainty = pd.to_numeric(
            timing["capture_clock_uncertainty_us"], errors="coerce"
        ).to_numpy()
        bound = float(np.max(uncertainty)) if np.isfinite(uncertainty).all() else None
        return (
            (captured - origin_ns) / 1e9,
            "transmitter enqueue mapped by USB affine fit (BLE)",
            bound,
        )
    host_times = (
        timing["host_receive_monotonic_ns"].to_numpy(dtype=np.int64) - origin_ns
    ) / 1e9
    fallback = (host_times, "host receive (USB buffering included)", None)
    if not sync_path.is_file() or "rx_callback_timestamp_us" not in timing:
        return fallback
    callbacks = pd.to_numeric(
        timing["rx_callback_timestamp_us"], errors="coerce"
    ).to_numpy()
    if not np.isfinite(callbacks).all():
        return fallback
    sync = pd.read_csv(sync_path)
    if sync.empty or sync["receiver_boot_id"].nunique() != 1:
        return fallback
    # The legacy gateway uses transmitter time as its reference. Only the USB
    # exchange (zero radio timestamps) has the same host clock as phase events.
    if not (sync["rx_radio_t2_us"].eq(0) & sync["tx_radio_t4_us"].eq(0)).all():
        return fallback
    estimator = ClockSyncEstimator()
    for row in sync.sort_values("host_receive_monotonic_ns").itertuples(index=False):
        sample = ClockSyncSample(
            sync_id=int(row.sync_id),
            sensing_sequence=int(row.sensing_sequence),
            receiver_boot_id=int(row.receiver_boot_id),
            tx_t1_us=int(row.tx_t1_us),
            rx_t2_us=int(row.rx_t2_us),
            rx_t3_us=int(row.rx_t3_us),
            tx_t4_us=int(row.tx_t4_us),
            rx_radio_t2_us=int(row.rx_radio_t2_us),
            tx_radio_t4_us=int(row.tx_radio_t4_us),
            receiver_mac=str(row.receiver_mac),
        )
        if (
            sample.round_trip_us < 0
            or sample.tx_t4_us < sample.tx_t1_us
            or sample.rx_t3_us < sample.rx_t2_us
        ):
            raise ValueError("Invalid clock-sync exchange")
        estimator.add(sample)
    estimate = estimator.estimate
    mapped = np.fromiter(
        (estimate.receiver_to_transmitter(value) for value in callbacks), dtype=float
    )
    seconds = (mapped - origin_ns / 1000) / 1e6
    return seconds, "receiver callback → host (USB affine fit)", estimate.uncertainty_us
