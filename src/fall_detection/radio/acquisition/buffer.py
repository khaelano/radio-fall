"""Thread-safe rolling state for live CSI display."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import nan
from threading import Lock
from typing import Optional
from collections.abc import Callable
import time

from .protocol import CsiRecord


DEFAULT_NOMINAL_RATE_HZ = 50


class PreviewNotReady(Exception):
    """The captured preview window still contains unprepared phase records."""


@dataclass(frozen=True)
class BufferSnapshot:
    """Immutable snapshot consumed by the GUI."""

    timestamps: tuple[float, ...]
    amplitudes: tuple[tuple[float, ...], ...]
    start_sequence: Optional[int]
    end_sequence: Optional[int]
    max_subcarriers: int
    # Keep the first five fields stable for small offline callers that create
    # snapshots positionally.  The additional views are parallel to
    # ``timestamps`` and use the same selected subcarrier slice.
    phases: tuple[tuple[float, ...], ...] = ()
    real: tuple[tuple[float, ...], ...] = ()
    imaginary: tuple[tuple[float, ...], ...] = ()
    rssi: tuple[int, ...] = ()
    noise_floor: tuple[int, ...] = ()
    phase_subcarriers: tuple[int, ...] = ()
    phase_amplitudes: tuple[tuple[float, ...], ...] = ()
    raw_phases: tuple[tuple[float, ...], ...] = ()
    calibrated_phases: tuple[tuple[float, ...], ...] = ()
    mean_i: tuple[float, ...] = ()
    mean_q: tuple[float, ...] = ()


@dataclass(frozen=True)
class RadioMonitorSnapshot:
    """Scalar-only radio traces for lightweight collection monitoring."""

    timestamps: tuple[float, ...]
    mean_i: tuple[float, ...]
    mean_q: tuple[float, ...]
    rssi: tuple[int, ...]
    noise_floor: tuple[int, ...]


class RollingCsiBuffer:
    """Keep a time-bounded history and track forward sequence gaps.

    ``max_records`` is a safety ceiling, not the normal retention policy.  A
    live stream passes a generous ceiling so that the configured ``seconds``
    window remains ten seconds even when the sender rate differs from the
    nominal rate.  The default retains the historical count-based behavior
    for small offline callers that do not supply a ceiling.
    """

    def __init__(
        self,
        nominal_rate: int = DEFAULT_NOMINAL_RATE_HZ,
        seconds: int = 10,
        *,
        max_records: Optional[int] = None,
        reorder_window: int = 128,
    ) -> None:
        self._seconds = max(1, seconds)
        self._max_records = (
            max(1, nominal_rate * self._seconds)
            if max_records is None
            else max(1, max_records)
        )
        self._records: deque[tuple[CsiRecord, int]] = deque()
        self._lock = Lock()
        self._last_sequence: Optional[int] = None
        self._missing_sequences = 0
        self._received_records = 0
        self._pending_missing: set[int] = set()
        self._reorder_window = max(0, reorder_window)
        self._last_timestamp_raw: Optional[int] = None
        self._last_timestamp_unwrapped: Optional[int] = None
        self._timestamp_offset = 0
        self._time_origin_us: Optional[int] = None

    @property
    def missing_sequences(self) -> int:
        with self._lock:
            return self._missing_sequences

    @property
    def received_records(self) -> int:
        with self._lock:
            return self._received_records

    @property
    def last_sequence(self) -> Optional[int]:
        with self._lock:
            return self._last_sequence

    def append(self, record: CsiRecord) -> None:
        with self._lock:
            sequence = record.sequence & 0xFFFFFFFF
            sequence_advanced = False
            late_reordered = False
            if self._last_sequence is None:
                self._last_sequence = sequence
                sequence_advanced = True
            else:
                forward = (sequence - self._last_sequence) & 0xFFFFFFFF
                if 0 < forward < 0x80000000:
                    sequence_advanced = True
                    gap = forward - 1
                    self._missing_sequences += gap
                    if gap and self._reorder_window:
                        # Keep only a bounded set of recently missing values;
                        # very large gaps are counted but cannot exhaust RAM.
                        start = max(1, gap - self._reorder_window + 1)
                        self._pending_missing.update(
                            (self._last_sequence + offset) & 0xFFFFFFFF
                            for offset in range(start, gap + 1)
                        )
                    self._last_sequence = sequence
                elif sequence in self._pending_missing:
                    late_reordered = True
                    self._pending_missing.remove(sequence)
                    self._missing_sequences = max(0, self._missing_sequences - 1)
                elif forward >= 0x80000000:
                    # A backwards jump that is not a nearby reorder is most
                    # likely a sender reboot. Start a new sequence epoch.
                    self._pending_missing.clear()
                    self._last_sequence = sequence
                    sequence_advanced = True

            raw_timestamp = record.timestamp_us & 0xFFFFFFFF
            if self._last_timestamp_raw is not None:
                delta = raw_timestamp - self._last_timestamp_raw
                if delta < -0x80000000:
                    self._timestamp_offset += 1 << 32
                elif delta < 0 and sequence_advanced and not late_reordered:
                    # A sender reboot resets its microsecond counter without
                    # the large negative jump characteristic of uint32 wrap.
                    # Continue the monotonic plotting epoch at the next tick.
                    self._timestamp_offset = (
                        self._last_timestamp_unwrapped + 1 - raw_timestamp
                    )
                candidate = raw_timestamp + self._timestamp_offset
                if self._last_timestamp_unwrapped is not None:
                    # Ignore small backwards jumps from reordered frames or a
                    # device restart so the plot's time axis stays monotonic.
                    candidate = max(candidate, self._last_timestamp_unwrapped)
            else:
                candidate = raw_timestamp
                self._time_origin_us = candidate
            self._last_timestamp_raw = raw_timestamp
            self._last_timestamp_unwrapped = candidate

            self._received_records += 1
            self._records.append((record, candidate))
            cutoff = candidate - self._seconds * 1_000_000
            while self._records and (
                self._records[0][1] < cutoff or len(self._records) > self._max_records
            ):
                self._records.popleft()

    def _window_entries(
        self, seconds: float | None
    ) -> tuple[tuple[tuple[CsiRecord, int], ...], int | None]:
        with self._lock:
            entries = tuple(self._records)
            origin = self._time_origin_us
        if entries and seconds is not None:
            cutoff = entries[-1][1] - max(0.0, seconds) * 1_000_000
            first_visible = next(
                (
                    index
                    for index, (_, timestamp) in enumerate(entries)
                    if timestamp >= cutoff
                ),
                len(entries) - 1,
            )
            entries = entries[first_visible:]
        return entries, origin

    def prepare_phase_views(
        self,
        *,
        seconds: float,
        max_records: int = 16,
        budget_ns: int = 8_000_000,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> bool:
        """Warm a bounded amount of preview work; return true when the window is ready.

        Cold receiver switches must not calibrate a whole window in one GUI
        callback. This only warms per-record caches; it never removes records
        or changes the complete snapshots used by other callers.
        """
        if max_records < 1 or budget_ns < 1:
            raise ValueError("preview preparation limits must be positive")
        entries, _ = self._window_entries(seconds)
        started, prepared = clock_ns(), 0
        for record, _timestamp in entries:
            if record.phase_views_ready:
                continue
            if prepared >= max_records or clock_ns() - started >= budget_ns:
                return False
            _ = record.channel_estimate_block
            prepared += 1
        return True

    def snapshot(
        self,
        start: int = 0,
        end: Optional[int] = None,
        *,
        seconds: Optional[float] = None,
        include_raw_views: bool = True,
        prepared_only: bool = False,
    ) -> BufferSnapshot:
        """Return a subcarrier slice, optionally limited to recent seconds.

        Phase displays can omit full raw CSI matrices: calibrated LTF views
        and the cached scalar I/Q means provide everything their plots need.
        """

        entries, origin = self._window_entries(seconds)
        if not entries:
            return BufferSnapshot((), (), None, None, 0)

        records = tuple(entry[0] for entry in entries)
        # Check the exact immutable window used below. The acquisition thread
        # can append a fresh burst after prepare_phase_views reported ready.
        # Never calibrate that burst synchronously outside its GUI work budget.
        if prepared_only and any(not record.phase_views_ready for record in records):
            raise PreviewNotReady

        maximum = max(
            getattr(record, "sample_count", None) or len(record.csi)
            for record in records
        )
        selected_end = maximum if end is None else max(start, min(end, maximum))
        selected_start = max(0, min(start, selected_end))
        amplitudes = phases = real = imaginary = ()
        if include_raw_views:
            amplitudes = tuple(
                tuple(record.amplitudes[selected_start:selected_end])
                for record in records
            )
            phases = tuple(
                tuple(record.phases[selected_start:selected_end]) for record in records
            )
            real = tuple(
                tuple(record.real[selected_start:selected_end]) for record in records
            )
            imaginary = tuple(
                tuple(record.imaginary[selected_start:selected_end])
                for record in records
            )
        phase_blocks = tuple(record.channel_estimate_block for record in records)
        phase_block = next((block for block in phase_blocks if block is not None), None)
        if phase_block is None:
            phase_subcarriers: tuple[int, ...] = ()
            phase_amplitudes: tuple[tuple[float, ...], ...] = ()
            raw_phases: tuple[tuple[float, ...], ...] = ()
            calibrated_phases: tuple[tuple[float, ...], ...] = ()
        else:
            phase_width = len(phase_block.subcarrier_indices)
            phase_start = min(max(0, start), phase_width)
            phase_end = (
                phase_width if end is None else min(phase_width, max(phase_start, end))
            )
            phase_subcarriers = phase_block.subcarrier_indices[phase_start:phase_end]
            row_width = phase_end - phase_start
            empty_phase = (nan,) * row_width
            phase_amplitudes = tuple(
                (
                    block.amplitudes[phase_start:phase_end]
                    if block is not None
                    and block.subcarrier_indices == phase_block.subcarrier_indices
                    else empty_phase
                )
                for block in phase_blocks
            )
            raw_phases = tuple(
                (
                    block.raw_phases[phase_start:phase_end]
                    if block is not None
                    and block.subcarrier_indices == phase_block.subcarrier_indices
                    else empty_phase
                )
                for block in phase_blocks
            )
            calibrated_phases = tuple(
                (
                    block.calibrated_phases[phase_start:phase_end]
                    if block is not None
                    and block.subcarrier_indices == phase_block.subcarrier_indices
                    else empty_phase
                )
                for block in phase_blocks
            )
        if origin is None:
            origin = entries[0][1]
        timestamps = tuple((entry[1] - origin) / 1_000_000.0 for entry in entries)
        return BufferSnapshot(
            timestamps=timestamps,
            amplitudes=amplitudes,
            start_sequence=records[0].sequence,
            end_sequence=records[-1].sequence,
            max_subcarriers=maximum,
            phases=phases,
            real=real,
            imaginary=imaginary,
            rssi=tuple(record.rssi for record in records),
            noise_floor=tuple(record.noise_floor for record in records),
            phase_subcarriers=phase_subcarriers,
            phase_amplitudes=phase_amplitudes,
            raw_phases=raw_phases,
            calibrated_phases=calibrated_phases,
            mean_i=(
                tuple(record.mean_i for record in records)
                if selected_start == 0 and selected_end == maximum
                else ()
            ),
            mean_q=(
                tuple(record.mean_q for record in records)
                if selected_start == 0 and selected_end == maximum
                else ()
            ),
        )

    def monitor_snapshot(
        self,
        *,
        seconds: float = 3.0,
        max_points: int = 90,
    ) -> RadioMonitorSnapshot:
        """Return downsampled scalar traces without constructing CSI matrices."""

        if max_points < 1:
            raise ValueError("max_points must be positive")
        with self._lock:
            entries = tuple(self._records)
            origin = self._time_origin_us

        if not entries:
            return RadioMonitorSnapshot((), (), (), (), ())

        cutoff = entries[-1][1] - max(0.0, seconds) * 1_000_000
        first_visible = next(
            (
                index
                for index, (_record, timestamp) in enumerate(entries)
                if timestamp >= cutoff
            ),
            len(entries) - 1,
        )
        entries = entries[first_visible:]
        if len(entries) > max_points:
            last = len(entries) - 1
            divisor = max_points - 1
            if divisor == 0:
                entries = entries[-1:]
            else:
                entries = tuple(
                    entries[index * last // divisor] for index in range(max_points)
                )

        if origin is None:
            origin = entries[0][1]
        records = tuple(record for record, _timestamp in entries)
        return RadioMonitorSnapshot(
            timestamps=tuple(
                (timestamp - origin) / 1_000_000.0 for _record, timestamp in entries
            ),
            mean_i=tuple(record.mean_i for record in records),
            mean_q=tuple(record.mean_q for record in records),
            rssi=tuple(record.rssi for record in records),
            noise_floor=tuple(record.noise_floor for record in records),
        )
