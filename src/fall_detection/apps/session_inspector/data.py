"""On-demand frame and signal loading for one recorded attempt.

Attempts are read from the typed frame tables derived from the raw journals
(the Rust ``radio_storage`` library). The CSV-style rows shown by the
inspector are synthesized from those frames, so the table layout is unchanged.
"""

from __future__ import annotations

import csv
import threading
from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from math import atan2, hypot
from typing import Any

import numpy as np
import pyarrow as pa

from fall_detection._radio_native import FrameStore, StorageError
from fall_detection.apps.common.rendering import PreparedCsiFrame, prepare_frame
from fall_detection.radio.buffer import BufferSnapshot
from fall_detection.radio.phase import (
    DEFAULT_PHASE_AMPLITUDE_FLOOR,
    HE20_COMPACT_SLOT_INDICES,
    HE20_SLOT_INDICES,
    HE20_VALID_SUBCARRIERS,
    HT20_SLOT_INDICES,
    HT20_VALID_SUBCARRIERS,
)
from fall_detection.radio.records import CSI_HEADER, CsiRecord, format_csi_record
from fall_detection.session import RecordedAttempt, attempt_indices

CancellationCallback = Callable[[], bool]
_FRAME_CACHE_SIZE = 4
_FRAME_CACHE_BYTES = 256 * 1024 * 1024
_FRAME_CACHE: OrderedDict[tuple[str, str, int, int, str], pa.Table] = OrderedDict()
_FRAME_CACHE_LOCK = threading.Lock()
MAX_PLOT_RECORDS = 800
CAPTURE_TIME_SOURCE = "capture → host clock; seconds from attempt start"
UNALIGNED_TIME_SOURCE = "receiver elapsed; not aligned to video"
RADIO_TIMING_HEADER = (
    "sequence",
    "transport_sequence",
    "tx_enqueue_timestamp_us",
    "rx_radio_timestamp_us",
    "rx_callback_timestamp_us",
    "host_receive_monotonic_ns",
    "capture_time_ns",
    "clock_uncertainty_us",
)
"""Columns of the radio timing table synthesized from frame timing columns."""
_TIMING_COLUMNS = (
    "sequence",
    "transport_sequence",
    "tx_enqueue_us",
    "rx_radio_us",
    "rx_callback_us",
    "host_arrival_ns",
    "capture_time_ns",
    "capture_uncertainty_us",
)
_FRAME_COLUMNS = (
    "transmitter_mac",
    "run_id",
    "tx_boot_id",
    "rx_boot_id",
    "sequence",
    "transport_sequence",
    "capture_time_ns",
    "capture_uncertainty_us",
    "host_arrival_ns",
    "rx_radio_us",
    "tx_enqueue_us",
    "rx_callback_us",
    "rssi",
    "noise_floor",
    "rate",
    "sig_mode",
    "mcs",
    "bandwidth",
    "smoothing",
    "not_sounding",
    "aggregation",
    "stbc",
    "fec_coding",
    "sgi",
    "ampdu_cnt",
    "channel",
    "secondary_channel",
    "ant",
    "rx_state",
    "sig_len",
    "first_word_invalid",
    "csi",
)


def timed_phase_image(times: np.ndarray, phase: np.ndarray) -> np.ndarray:
    """Place the latest phase sample in each uniform display cell; retain gaps."""
    image = np.full((phase.shape[1], len(times)), np.nan, dtype=phase.dtype)
    if not len(times):
        return image
    duration = max(1e-6, float(times[-1] - times[0]))
    bins = np.clip(
        ((times - times[0]) / duration * len(times)).astype(int), 0, len(times) - 1
    )
    for row, index in enumerate(bins):
        image[:, index] = phase[row]
    return image


class DataLoadCancelled(RuntimeError):
    """Raised when an asynchronous attempt load becomes stale."""


@dataclass(frozen=True)
class TableData:
    """Textual rows of one table shown by the inspector."""

    name: str
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def row_count(self) -> int:
        """Return the number of data rows."""

        return len(self.rows)


@dataclass(frozen=True)
class AttemptData:
    """Tables and parsed CSI records for one attempt receiver."""

    attempt_key: str
    receiver_id: str
    csi: TableData
    radio_timing: TableData
    records: tuple[CsiRecord, ...]
    record_row_indices: tuple[int, ...]
    total_record_count: int | None = None
    snapshot: BufferSnapshot | None = None
    prepared_frame: PreparedCsiFrame | None = None
    warnings: tuple[str, ...] = ()
    signal_times: tuple[float, ...] | None = None
    time_source: str = UNALIGNED_TIME_SOURCE
    attempt: RecordedAttempt | None = None
    """Source attempt; lets a compact UI load rebuild one record on demand."""
    frames_fingerprint: str | None = None
    """Source fingerprint of the frame tables this load read; pins row identity."""

    @property
    def record_count(self) -> int:
        """Return the number of valid records, including compact UI loads."""

        return (
            len(self.records)
            if self.total_record_count is None
            else self.total_record_count
        )


@dataclass(frozen=True)
class CsiValueRow:
    """One exact complex value for the selected CSI record."""

    subcarrier: str
    real: float
    imaginary: float
    amplitude: float
    raw_phase: float
    calibrated_phase: float | None


def _check_cancelled(cancelled: CancellationCallback | None) -> None:
    if cancelled is not None and cancelled():
        raise DataLoadCancelled("attempt data load cancelled")


def _split_row(line: str) -> tuple[str, ...]:
    return tuple(next(csv.reader([line])))


def _frame_record(frame: dict[str, Any], index: int) -> CsiRecord:
    """Build the record of frame ``index`` from its columns.

    The payload holds interleaved imaginary and real bytes. The first two values
    of a frame flagged ``first_word_invalid`` stay in ``raw_csi`` but are not
    plottable.
    """

    payload = np.frombuffer(frame["csi"][index], dtype=np.int8)
    raw = tuple((payload[1::2].astype(np.float64) + 1j * payload[0::2]).tolist())
    invalid = bool(frame["first_word_invalid"][index])
    shown = (complex(np.nan, np.nan),) * min(2, len(raw)) + raw[2:] if invalid else raw
    return CsiRecord(
        sequence=frame["sequence"][index],
        mac=frame["transmitter_mac"][index],
        rssi=frame["rssi"][index],
        noise_floor=frame["noise_floor"][index],
        timestamp_us=frame["rx_radio_us"][index],
        csi=shown,
        transport_sequence=frame["transport_sequence"][index],
        run_id=frame["run_id"][index],
        transmitter_boot_id=frame["tx_boot_id"][index],
        receiver_boot_id=frame["rx_boot_id"][index],
        capture_host_monotonic_ns=frame["capture_time_ns"][index],
        capture_clock_uncertainty_us=frame["capture_uncertainty_us"][index],
        tx_timestamp_us=frame["tx_enqueue_us"][index],
        rx_callback_timestamp_us=frame["rx_callback_us"][index],
        first_word_invalid=invalid,
        rate=frame["rate"][index],
        sig_mode=frame["sig_mode"][index],
        mcs=frame["mcs"][index],
        bandwidth=frame["bandwidth"][index],
        smoothing=frame["smoothing"][index],
        not_sounding=frame["not_sounding"][index],
        aggregation=frame["aggregation"][index],
        stbc=frame["stbc"][index],
        fec_coding=frame["fec_coding"][index],
        sgi=frame["sgi"][index],
        ampdu_count=frame["ampdu_cnt"][index],
        channel=frame["channel"][index],
        secondary_channel=frame["secondary_channel"][index],
        antenna=frame["ant"][index],
        sig_len=frame["sig_len"][index],
        rx_state=frame["rx_state"][index],
        csi_length=payload.size,
        raw_csi=raw,
    )


def _frame_tables(
    frames: pa.Table,
    start_ns: int,
    *,
    cancelled: CancellationCallback | None = None,
) -> tuple[TableData, TableData, tuple[CsiRecord, ...], tuple[float, ...] | None]:
    """Synthesize CSV-style tables, records and plot times from attempt frames.

    Rows keep journal (delivery) order. Times are capture times relative to the
    attempt start, one per record, or ``None`` when there are no frames.
    """

    frame = frames.select(_FRAME_COLUMNS).to_pydict()
    records: list[CsiRecord] = []
    csi_rows: list[tuple[str, ...]] = []
    timing_rows: list[tuple[str, ...]] = []
    for index in range(frames.num_rows):
        if index % 128 == 0:
            _check_cancelled(cancelled)
        record = _frame_record(frame, index)
        records.append(record)
        csi_rows.append(_split_row(format_csi_record(record)))
        timing_rows.append(tuple(str(frame[name][index]) for name in _TIMING_COLUMNS))
    times = (
        tuple((value - start_ns) / 1e9 for value in frame["capture_time_ns"])
        if records
        else None
    )
    return (
        TableData("CSI", _split_row(CSI_HEADER), tuple(csi_rows)),
        TableData("Radio timing", RADIO_TIMING_HEADER, tuple(timing_rows)),
        tuple(records),
        times,
    )


def _snapshot(
    records: Iterable[CsiRecord],
    *,
    cancelled: CancellationCallback | None = None,
) -> BufferSnapshot:
    records = tuple(records)
    if not records:
        return BufferSnapshot((), (), None, None, 0)
    if len(records) > MAX_PLOT_RECORDS:
        indices = downsample_indices(len(records), MAX_PLOT_RECORDS)
        records = tuple(records[index] for index in indices)
    for index in range(0, len(records), 64):
        _check_cancelled(cancelled)
    return _vectorized_snapshot(records)


def _phase_layout(
    record: CsiRecord,
) -> tuple[tuple[int, ...], frozenset[int], int] | None:
    """Return the channel-estimate layout without constructing LTF objects."""

    count = len(record.raw_csi)
    if record.bandwidth != 0:
        return None
    if record.sig_mode == 4 and not record.stbc:
        if count == len(HE20_SLOT_INDICES):
            return HE20_SLOT_INDICES, HE20_VALID_SUBCARRIERS, 0
        if count == len(HE20_COMPACT_SLOT_INDICES):
            return HE20_COMPACT_SLOT_INDICES, HE20_VALID_SUBCARRIERS, 0
        return None
    if count % len(HT20_SLOT_INDICES):
        return None
    blocks = count // len(HT20_SLOT_INDICES)
    if record.sig_mode == 1 and (
        (not record.stbc and blocks == 2) or (record.stbc and blocks == 3)
    ):
        return HT20_SLOT_INDICES, HT20_VALID_SUBCARRIERS, len(HT20_SLOT_INDICES)
    return None


def _unwrapped_timestamps(records: tuple[CsiRecord, ...]) -> tuple[float, ...]:
    """Build a monotonic plotting clock across uint32 wrap and radio restarts."""

    values: list[int] = []
    offset = 0
    last_raw: int | None = None
    last_unwrapped: int | None = None
    for record in records:
        raw = record.timestamp_us & 0xFFFFFFFF
        if last_raw is None:
            candidate = raw
        else:
            delta = raw - last_raw
            if delta < -0x80000000:
                offset += 1 << 32
            elif delta < 0 and last_unwrapped is not None:
                offset = last_unwrapped + 1 - raw
            candidate = raw + offset
            if last_unwrapped is not None:
                candidate = max(candidate, last_unwrapped)
        values.append(candidate)
        last_raw = raw
        last_unwrapped = candidate
    origin = values[0]
    return tuple((value - origin) / 1_000_000.0 for value in values)


def _vectorized_snapshot(records: tuple[CsiRecord, ...]) -> BufferSnapshot:
    """Prepare offline CSI matrices without per-record LTF object creation.

    This implements the same phase mask and weighted linear detrending used by
    ``LtfBlock`` while batching amplitude/angle work in NumPy. It is roughly an
    order of magnitude faster on collection attempts and releases the GIL for
    most of the numerical work.
    """

    row_count = len(records)
    maximum = max(len(record.csi) for record in records)
    csi = np.full((row_count, maximum), np.nan + 1j * np.nan, dtype=np.complex128)
    for row, record in enumerate(records):
        csi[row, : len(record.csi)] = record.csi
    amplitudes = np.abs(csi)
    phases = np.angle(csi)

    chosen = next(
        (layout for record in records if (layout := _phase_layout(record)) is not None),
        None,
    )
    if chosen is None:
        phase_subcarriers: tuple[int, ...] = ()
        phase_amplitudes = np.empty((row_count, 0), dtype=np.float64)
        raw_phases = np.empty((row_count, 0), dtype=np.float64)
        calibrated = np.empty((row_count, 0), dtype=np.float64)
    else:
        layout_indices, valid_subcarriers, offset = chosen
        order = np.argsort(np.asarray(layout_indices, dtype=np.int32))
        serialized_order = np.argsort(order)
        ordered_indices = np.asarray(layout_indices, dtype=np.float64)[order]
        width = len(layout_indices)
        channel = np.full(
            (row_count, width),
            np.nan + 1j * np.nan,
            dtype=np.complex128,
        )
        compatible: list[int] = []
        for row, record in enumerate(records):
            if _phase_layout(record) != chosen:
                continue
            block = np.asarray(
                record.raw_csi[offset : offset + width], dtype=np.complex128
            )
            if block.size != width:
                continue
            channel[row] = block[order]
            compatible.append(row)

        phase_amplitudes = np.abs(channel)
        channel_angles = np.angle(channel)
        carrier_mask = np.asarray(
            [int(index) in valid_subcarriers for index in ordered_indices],
            dtype=bool,
        )
        valid = (
            np.isfinite(channel.real)
            & np.isfinite(channel.imag)
            & np.isfinite(phase_amplitudes)
            & (phase_amplitudes >= DEFAULT_PHASE_AMPLITUDE_FLOOR)
            & carrier_mask[None, :]
        )
        if offset == 0:
            for row in compatible:
                if records[row].first_word_invalid:
                    valid[row, serialized_order[:2]] = False
        raw_phases = np.where(valid, channel_angles, np.nan)
        calibrated = np.full(channel_angles.shape, np.nan, dtype=np.float64)
        for row in compatible:
            mask = valid[row]
            if int(mask.sum()) < 3:
                continue
            x = ordered_indices[mask]
            y = np.unwrap(channel_angles[row, mask])
            weights = np.maximum(
                phase_amplitudes[row, mask], DEFAULT_PHASE_AMPLITUDE_FLOOR
            )
            sum_w = weights.sum()
            sum_wx = np.sum(weights * x)
            sum_wy = np.sum(weights * y)
            sum_wxx = np.sum(weights * x * x)
            sum_wxy = np.sum(weights * x * y)
            denominator = sum_w * sum_wxx - sum_wx * sum_wx
            if denominator == 0:
                continue
            slope = (sum_w * sum_wxy - sum_wx * sum_wy) / denominator
            intercept = (sum_wy - slope * sum_wx) / sum_w
            residual = y - (slope * x + intercept)
            calibrated[row, mask] = (residual + np.pi) % (2.0 * np.pi) - np.pi
        # ``RollingCsiBuffer`` exposes the radio's serialized slot order. Keep
        # that contract here; ``prepare_frame`` performs the display sorting.
        phase_amplitudes = phase_amplitudes[:, serialized_order]
        raw_phases = raw_phases[:, serialized_order]
        calibrated = calibrated[:, serialized_order]
        phase_subcarriers = tuple(layout_indices)

    return BufferSnapshot(
        timestamps=_unwrapped_timestamps(records),
        amplitudes=amplitudes,
        start_sequence=records[0].sequence,
        end_sequence=records[-1].sequence,
        max_subcarriers=maximum,
        phases=phases,
        real=csi.real,
        imaginary=csi.imag,
        rssi=tuple(record.rssi for record in records),
        noise_floor=tuple(record.noise_floor for record in records),
        phase_subcarriers=phase_subcarriers,
        phase_amplitudes=phase_amplitudes,
        raw_phases=raw_phases,
        calibrated_phases=calibrated,
    )


def load_attempt_data(
    attempt: RecordedAttempt,
    receiver_id: str,
    *,
    prepare_signals: bool = False,
    cancelled: CancellationCallback | None = None,
) -> AttemptData:
    """Load one receiver's frames in an attempt window.

    The frame tables are converted from the raw journals when missing or stale.
    Signal matrices are intentionally deferred by default. They require phase
    calibration for every record and are only needed when the Signals tab is
    shown. Use :func:`prepare_attempt_signals` to enrich a loaded result in a
    worker thread.

    Args:
        attempt: Attempt returned by :func:`~.models.load_session`.
        receiver_id: Receiver whose frames are loaded.
        prepare_signals: Also build the plot matrices.
        cancelled: Optional callback returning ``True`` to abort the load.

    Returns:
        The tables, records and plot times of the recording.

    Raises:
        DataLoadCancelled: If ``cancelled`` reports cancellation.
        ValueError: If the frame tables hold no window for the attempt.
    """

    session = FrameStore.ensure(str(attempt.session_path), str(attempt.frames_path))
    _check_cancelled(cancelled)
    index = attempt_indices(session).get(
        (attempt.trial_ordinal, attempt.attempt_number)
    )
    if index is None:
        raise ValueError(f"no frame window for attempt {attempt.key}")
    start_ns = pa.table(session.attempts()).column("start_ns")[index].as_py()
    frames = pa.table(
        session.attempt_frames(index, receiver_id, columns=_FRAME_COLUMNS)
    )
    _check_cancelled(cancelled)
    csi, timing, records, times = _frame_tables(frames, start_ns, cancelled=cancelled)
    warnings = (
        () if frames.num_rows else (f"no frames from {receiver_id} in this attempt",)
    )
    result = AttemptData(
        attempt_key=attempt.key,
        receiver_id=receiver_id,
        csi=csi,
        radio_timing=timing,
        records=records,
        record_row_indices=tuple(range(len(records))),
        total_record_count=len(records),
        warnings=warnings,
        signal_times=times,
        time_source=CAPTURE_TIME_SOURCE if times is not None else UNALIGNED_TIME_SOURCE,
        attempt=attempt,
        frames_fingerprint=session.source_fingerprint,
    )
    return (
        prepare_attempt_signals(result, cancelled=cancelled)
        if prepare_signals
        else result
    )


def load_attempt_data_for_ui(
    attempt: RecordedAttempt,
    receiver_id: str,
    *,
    prepare_signals: bool = False,
) -> AttemptData:
    """Load UI data while omitting expensive-to-transfer intermediate state.

    Session inspector workers run this function in a separate process. The
    exact table rows and prepared plot arrays remain available, while parsed
    ``CsiRecord`` objects and the intermediate snapshot are discarded before
    inter-process serialization. A selected value row is rebuilt on demand from
    the frame tables by :func:`csi_record_for_table_row`.
    """

    data = load_attempt_data(
        attempt,
        receiver_id,
        prepare_signals=prepare_signals,
    )
    return replace(data, records=(), snapshot=None)


def csi_record_for_table_row(
    data: AttemptData,
    source_row: int,
) -> CsiRecord | None:
    """Return the record behind one CSI table row for value inspection.

    Rows are in frame order, so ``source_row`` indexes the receiver's frames in
    the attempt. Compact UI loads carry no records; the row's frame is then read
    from the frame tables the load used (opened read-only, never converted, and
    cached per attempt and receiver). ``None`` is returned if those tables have
    since changed.
    """

    if not 0 <= source_row < len(data.csi.rows):
        return None
    if data.records:
        try:
            record_index = data.record_row_indices.index(source_row)
        except ValueError:
            return None
        return data.records[record_index]
    frames = _receiver_frames(data)
    if frames is None or source_row >= frames.num_rows:
        return None
    return _frame_record(frames.slice(source_row, 1).to_pydict(), 0)


def _receiver_frames(data: AttemptData) -> pa.Table | None:
    """Return the receiver's attempt frames for a compact load, cached.

    The tables are opened read-only and never converted, so this is safe on the
    GUI thread. The cache key includes the source fingerprint recorded by the
    load, and a table whose fingerprint differs (re-converted since the load)
    yields ``None`` rather than rows that no longer match the displayed table.
    """

    attempt = data.attempt
    if attempt is None or data.frames_fingerprint is None:
        return None
    key = (
        str(attempt.frames_path),
        data.frames_fingerprint,
        attempt.trial_ordinal,
        attempt.attempt_number,
        data.receiver_id,
    )
    with _FRAME_CACHE_LOCK:
        cached = _FRAME_CACHE.get(key)
        if cached is not None:
            _FRAME_CACHE.move_to_end(key)
            return cached
    try:
        session = FrameStore.open(str(attempt.frames_path))
        if session.source_fingerprint != data.frames_fingerprint:
            return None
        index = attempt_indices(session).get(
            (attempt.trial_ordinal, attempt.attempt_number)
        )
        if index is None:
            return None
        frames = pa.table(
            session.attempt_frames(index, data.receiver_id, columns=_FRAME_COLUMNS)
        )
        # A re-conversion renames the tables before it rewrites the manifest, so
        # confirm the fingerprint did not change while the rows were read.
        if FrameStore.open(str(attempt.frames_path)).source_fingerprint != (
            data.frames_fingerprint
        ):
            return None
    except StorageError:
        return None
    with _FRAME_CACHE_LOCK:
        _FRAME_CACHE[key] = frames
        while len(_FRAME_CACHE) > _FRAME_CACHE_SIZE or (
            len(_FRAME_CACHE) > 1
            and sum(table.nbytes for table in _FRAME_CACHE.values())
            > _FRAME_CACHE_BYTES
        ):
            _FRAME_CACHE.popitem(last=False)
    return frames


def prepare_attempt_signals(
    data: AttemptData,
    *,
    cancelled: CancellationCallback | None = None,
) -> AttemptData:
    """Build the expensive signal matrices for a previously loaded attempt."""

    if data.prepared_frame is not None and data.snapshot is not None:
        return data
    _check_cancelled(cancelled)
    records = data.records
    times = data.signal_times
    if times is not None:
        indices = np.argsort(times, kind="stable")
        indices = indices[list(downsample_indices(len(indices), MAX_PLOT_RECORDS))]
        records = tuple(records[index] for index in indices)
        times = tuple(times[index] for index in indices)
    snapshot = _snapshot(records, cancelled=cancelled)
    if times is not None:
        snapshot = replace(snapshot, timestamps=times)
    _check_cancelled(cancelled)
    prepared = prepare_frame(
        snapshot,
        phase_mode="calibrated",
        phase_mode_change="change",
        phase_mode_raw="raw",
        window_seconds=3.0,
    )
    # The shared live renderer rebases its last packet to zero. Offline aligned
    # plots instead share attempt-start zero with video, across every receiver.
    if times is not None:
        prepared = replace(prepared, timestamps=np.asarray(times, dtype=np.float64))
    _check_cancelled(cancelled)
    return replace(data, snapshot=snapshot, prepared_frame=prepared)


def csi_value_rows(record: CsiRecord) -> tuple[CsiValueRow, ...]:
    """Return physical subcarrier values for an exact CSI record.

    When the frame layout cannot identify an HE/HT channel-estimate block, the
    fallback exposes every serialized complex slot by index.
    """

    block = record.channel_estimate_block
    if block is not None:
        return tuple(
            CsiValueRow(
                subcarrier=f"{subcarrier:+d}",
                real=float(value.real),
                imaginary=float(value.imag),
                amplitude=float(amplitude),
                raw_phase=float(raw_phase),
                calibrated_phase=float(calibrated_phase),
            )
            for subcarrier, value, amplitude, raw_phase, calibrated_phase in zip(
                block.subcarrier_indices,
                block.values,
                block.amplitudes,
                block.raw_phases,
                block.calibrated_phases,
                strict=True,
            )
        )
    values = record.raw_csi or record.csi
    return tuple(
        CsiValueRow(
            subcarrier=str(index),
            real=float(value.real),
            imaginary=float(value.imag),
            amplitude=hypot(value.real, value.imag),
            raw_phase=atan2(value.imag, value.real),
            calibrated_phase=None,
        )
        for index, value in enumerate(values)
    )


def downsample_indices(length: int, maximum: int = 2_000) -> tuple[int, ...]:
    """Return stable endpoint-preserving plot indices."""

    if maximum < 2:
        raise ValueError("maximum must be at least two")
    if length <= maximum:
        return tuple(range(length))
    last = length - 1
    divisor = maximum - 1
    return tuple(index * last // divisor for index in range(maximum))
