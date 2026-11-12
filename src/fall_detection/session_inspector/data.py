"""On-demand CSV and signal loading for one recorded attempt."""

from __future__ import annotations

import csv
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from io import StringIO
from math import atan2, hypot
from pathlib import Path

import numpy as np

from ..radio.acquisition.buffer import BufferSnapshot
from ..radio.acquisition.protocol import CsiRecord, parse_csi_line
from ..radio.preprocessing.phase import (
    DEFAULT_PHASE_AMPLITUDE_FLOOR,
    HE20_COMPACT_SLOT_INDICES,
    HE20_SLOT_INDICES,
    HE20_VALID_SUBCARRIERS,
    HT20_SLOT_INDICES,
    HT20_VALID_SUBCARRIERS,
)
from ..radio.preprocessing.rendering import PreparedCsiFrame, prepare_frame
from .models import RecordedAttempt

CancellationCallback = Callable[[], bool]
MAX_PLOT_RECORDS = 800


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
    """Exact textual contents of one CSV file."""

    name: str
    path: Path | None
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
    clock_sync: TableData
    records: tuple[CsiRecord, ...]
    record_row_indices: tuple[int, ...]
    total_record_count: int | None = None
    snapshot: BufferSnapshot | None = None
    prepared_frame: PreparedCsiFrame | None = None
    warnings: tuple[str, ...] = ()
    signal_times: tuple[float, ...] | None = None
    time_source: str = "receiver elapsed; not aligned to video"

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


def _normalize_row(row: list[str], width: int) -> tuple[str, ...]:
    if len(row) >= width:
        return tuple(row)
    return tuple(row + [""] * (width - len(row)))


def load_table(
    path: Path | None,
    name: str,
    *,
    cancelled: CancellationCallback | None = None,
) -> TableData:
    """Load a CSV exactly as text, preserving every parseable row."""

    if path is None:
        return TableData(name=name, path=None, warnings=(f"missing {name}",))
    warnings: list[str] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.reader(stream)
            try:
                headers = tuple(next(reader))
            except StopIteration:
                return TableData(
                    name=name,
                    path=path,
                    warnings=(f"{path.name} is empty",),
                )
            rows: list[tuple[str, ...]] = []
            for index, row in enumerate(reader, start=2):
                if index % 128 == 0:
                    _check_cancelled(cancelled)
                if len(row) != len(headers):
                    warnings.append(
                        f"{path.name}:{index}: expected {len(headers)} columns, got {len(row)}"
                    )
                rows.append(_normalize_row(row, len(headers)))
    except (OSError, csv.Error, UnicodeError) as exc:
        warnings.append(f"unable to read {path}: {exc}")
        return TableData(name=name, path=path, warnings=tuple(warnings))
    return TableData(
        name=name,
        path=path,
        headers=headers,
        rows=tuple(rows),
        warnings=tuple(warnings),
    )


def _load_csi(
    path: Path | None,
    *,
    cancelled: CancellationCallback | None = None,
) -> tuple[TableData, tuple[CsiRecord, ...], tuple[int, ...]]:
    if path is None:
        return TableData(name="CSI", path=None, warnings=("missing CSI",)), (), ()
    warnings: list[str] = []
    records: list[CsiRecord] = []
    record_row_indices: list[int] = []
    rows: list[tuple[str, ...]] = []
    headers: tuple[str, ...] = ()
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            header_line = next(stream, None)
            if header_line is None:
                return (
                    TableData(
                        name="CSI",
                        path=path,
                        warnings=(f"{path.name} is empty",),
                    ),
                    (),
                    (),
                )
            headers = tuple(next(csv.reader([header_line])))
            for line_number, line in enumerate(stream, start=2):
                if line_number % 128 == 0:
                    _check_cancelled(cancelled)
                try:
                    row = next(csv.reader([line]))
                except csv.Error as exc:
                    warnings.append(f"{path.name}:{line_number}: {exc}")
                    row = []
                if len(row) != len(headers):
                    warnings.append(
                        f"{path.name}:{line_number}: expected {len(headers)} "
                        f"columns, got {len(row)}"
                    )
                rows.append(_normalize_row(row, len(headers)))
                try:
                    records.append(parse_csi_line(line))
                    record_row_indices.append(line_number - 2)
                except ValueError as exc:
                    warnings.append(f"{path.name}:{line_number}: {exc}")
    except (OSError, UnicodeError) as exc:
        warnings.append(f"unable to parse {path}: {exc}")
    return (
        TableData(
            name="CSI",
            path=path,
            headers=headers,
            rows=tuple(rows),
            warnings=tuple(dict.fromkeys(warnings)),
        ),
        tuple(records),
        tuple(record_row_indices),
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
    """Load one receiver's tables and parse its valid CSI records.

    Signal matrices are intentionally deferred by default. They require phase
    calibration for every record and are only needed when the Signals tab is
    shown. Use :func:`prepare_attempt_signals` to enrich a loaded result in a
    worker thread.
    """

    files = attempt.files_for(receiver_id)
    csi, records, record_row_indices = _load_csi(files.csi, cancelled=cancelled)
    _check_cancelled(cancelled)
    timing = load_table(files.radio_timing, "Radio timing", cancelled=cancelled)
    _check_cancelled(cancelled)
    clock = load_table(files.clock_sync, "Clock sync", cancelled=cancelled)
    _check_cancelled(cancelled)
    signal_times, time_source, clock_warnings = _attempt_times(
        attempt, receiver_id, records, record_row_indices, csi, timing, clock
    )
    warnings = tuple(
        dict.fromkeys(
            (*csi.warnings, *timing.warnings, *clock.warnings, *clock_warnings)
        )
    )
    result = AttemptData(
        attempt_key=attempt.key,
        receiver_id=receiver_id,
        csi=csi,
        radio_timing=timing,
        clock_sync=clock,
        records=records,
        record_row_indices=record_row_indices,
        total_record_count=len(records),
        warnings=warnings,
        signal_times=signal_times,
        time_source=time_source,
    )
    return (
        prepare_attempt_signals(result, cancelled=cancelled)
        if prepare_signals
        else result
    )


def _attempt_times(attempt, receiver_id, records, row_indices, csi, timing, clock):
    """Align derived signal plots; never change exact saved tables or raw order."""
    fallback = (None, "receiver elapsed; not aligned to video", ())
    origin = attempt.metadata.get("started_monotonic_ns")
    if not isinstance(origin, int) or not records:
        return fallback
    directory = attempt.path / "receivers" / receiver_id
    sidecar = next(
        (
            directory / name
            for name in ["gateway_timing.jsonl"]
            if (directory / name).is_file()
        ),
        None,
    )
    try:
        if sidecar is not None:
            rows = [
                json.loads(line)
                for line in sidecar.read_text().splitlines()
                if line.strip()
            ]
            if len(rows) != csi.row_count:
                raise ValueError("CSI/capture timing row counts differ")
            values = []
            for record, index in zip(records, row_indices, strict=True):
                row = rows[index]
                captured = row["capture_host_monotonic_ns"]
                if (
                    row["sequence"] != record.sequence
                    or row["rx_radio_timestamp_us"] != record.timestamp_us
                    or row.get("schema_version") != 1
                    or not isinstance(captured, int)
                    or isinstance(captured, bool)
                ):
                    raise ValueError("CSI/capture timing identities or clocks differ")
                values.append((captured - origin) / 1e9)
            return tuple(values), "capture → host clock; seconds from attempt start", ()
        if timing.row_count != csi.row_count:
            return fallback
        rows = [dict(zip(timing.headers, row, strict=True)) for row in timing.rows]
        selected = [rows[index] for index in row_indices]
        if any(
            int(row["sequence"]) != record.sequence
            for row, record in zip(selected, records, strict=True)
        ):
            raise ValueError("CSI/radio timing sequences differ")
        # Only USB clock exchanges use the host as reference. Gateway exchanges
        # must never be interpreted as receiver-to-host mappings.
        sync = [dict(zip(clock.headers, row, strict=True)) for row in clock.rows]
        if sync and all(
            int(row["rx_radio_t2_us"]) == int(row["tx_radio_t4_us"]) == 0
            for row in sync
        ):
            from ..radio.acquisition.clock_sync import (
                ClockSyncEstimator,
                ClockSyncSample,
            )

            if len({row["receiver_boot_id"] for row in sync}) != 1:
                raise ValueError("USB clock timing mixes receiver boots")
            estimator = ClockSyncEstimator()
            for row in sorted(
                sync, key=lambda row: int(row["host_receive_monotonic_ns"])
            ):
                fields = {
                    key: int(row[key])
                    for key in [
                        "sync_id",
                        "sensing_sequence",
                        "receiver_boot_id",
                        "tx_t1_us",
                        "rx_t2_us",
                        "rx_t3_us",
                        "tx_t4_us",
                        "rx_radio_t2_us",
                        "tx_radio_t4_us",
                    ]
                }
                sample = ClockSyncSample(**fields, receiver_mac=row["receiver_mac"])
                if (
                    sample.round_trip_us < 0
                    or sample.tx_t4_us < sample.tx_t1_us
                    or sample.rx_t3_us < sample.rx_t2_us
                ):
                    raise ValueError("Invalid USB clock-sync exchange")
                estimator.add(sample)
            estimate = estimator.estimate
            return (
                tuple(
                    (
                        estimate.receiver_to_transmitter(
                            int(row["rx_callback_timestamp_us"])
                        )
                        - origin / 1000
                    )
                    / 1e6
                    for row in selected
                ),
                "USB callback → host clock; seconds from attempt start",
                (),
            )
        return (
            tuple(
                (int(row["host_receive_monotonic_ns"]) - origin) / 1e9
                for row in selected
            ),
            "host receipt time (not sensing time); seconds from attempt start",
            (),
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, fallback[1], (f"Video/CSI alignment unavailable: {exc}",)


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
    inter-process serialization. A selected value row is parsed on demand by
    :func:`csi_record_for_table_row`.
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
    """Parse one exact CSI table row for on-demand value inspection."""

    if not 0 <= source_row < len(data.csi.rows):
        return None
    if data.records:
        try:
            record_index = data.record_row_indices.index(source_row)
        except ValueError:
            return None
        return data.records[record_index]
    stream = StringIO()
    csv.writer(stream, lineterminator="").writerow(data.csi.rows[source_row])
    try:
        return parse_csi_line(stream.getvalue())
    except ValueError:
        return None


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
