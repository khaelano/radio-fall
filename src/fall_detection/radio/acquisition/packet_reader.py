"""Shared ingestion state for binary CSI packet transports."""

from __future__ import annotations

from collections import deque
from dataclasses import replace
from pathlib import Path
import time
from typing import Callable, Optional

from .buffer import RollingCsiBuffer
from .protocol import CsiRecord
from .recorder import CsiRecorder
from .wire import CsiDatagramError, ReceiverStats, decode_csi_packet
from .telemetry import BackhaulTelemetrySnapshot


class BinaryCsiPacketReader:
    """Decode, validate, record, and track packets supplied by an adapter."""

    def __init__(
        self,
        buffer: RollingCsiBuffer,
        output_dir: Path,
        *,
        receiver_mac: Optional[str] = None,
        on_status: Optional[Callable[[str, bool], None]] = None,
        live_status: str = "binary CSI stream live",
        record_sink: Optional[Callable[[CsiRecord, int], None]] = None,
        profile_fingerprint: Optional[str] = None,
        require_profile_fingerprint: bool = False,
    ) -> None:
        self.buffer = buffer
        self.output_dir = output_dir
        self.receiver_mac = receiver_mac.lower() if receiver_mac else None
        self.on_status = on_status
        self.live_status = live_status
        self.record_sink = record_sink
        self.profile_fingerprint = profile_fingerprint
        self.require_profile_fingerprint = require_profile_fingerprint
        self.malformed_lines = 0
        self.duplicate_records = 0
        self._recent_keys: deque = deque(maxlen=2048)
        self._recent_key_set: set = set()
        self.total_packets = 0
        self.foreign_packets = 0
        self.batch_packets = 0
        self.legacy_packets = 0
        self.transport_missing = 0
        self.transport_reordered = 0
        self.last_transport_sequence: Optional[int] = None
        self.batch_missing = 0
        self.batch_reordered = 0
        self.last_batch_sequence: Optional[int] = None
        self.receiver_boot_id: Optional[int] = None
        self.receiver_restarts = 0
        self.receiver_stats: Optional[ReceiverStats] = None
        self.last_valid_time: Optional[float] = None
        self.firmware_messages: deque[str] = deque(maxlen=20)
        self._recorder: Optional[CsiRecorder] = None
        self._stream_live = False

    @property
    def total_datagrams(self) -> int:
        """Backward-compatible UDP counter name."""

        return self.total_packets

    @property
    def foreign_datagrams(self) -> int:
        """Backward-compatible UDP counter name."""

        return self.foreign_packets

    @property
    def batch_datagrams(self) -> int:
        """Backward-compatible UDP counter name."""

        return self.batch_packets

    def telemetry_snapshot(self) -> BackhaulTelemetrySnapshot:
        """Return a read-only snapshot of host and available firmware counters."""

        return BackhaulTelemetrySnapshot(
            captured_monotonic_ns=time.monotonic_ns(),
            records=self.buffer.received_records,
            batches=self.batch_packets,
            host_missing_sequences=self.buffer.missing_sequences,
            transport_missing=self.transport_missing,
            transport_reordered=self.transport_reordered,
            batch_missing=self.batch_missing,
            batch_reordered=self.batch_reordered,
            malformed=self.malformed_lines,
            foreign=self.foreign_packets,
            receiver_restarts=self.receiver_restarts,
            serial_frames=getattr(self, "serial_frames", None),
            receiver_boot_id=self.receiver_boot_id,
            receiver_stats=self.receiver_stats,
            transmitter_stats=getattr(self, "transmitter_stats", None),
            gateway_stats=getattr(self, "gateway_stats", None),
        )

    @property
    def legacy_datagrams(self) -> int:
        """Backward-compatible UDP counter name."""

        return self.legacy_packets

    def _status(self, message: str, connected: bool) -> None:
        if self.on_status is not None:
            self.on_status(message, connected)

    def _track_transport_sequence(self, sequence: int) -> None:
        if self.last_transport_sequence is None:
            self.last_transport_sequence = sequence
            return

        forward = (sequence - self.last_transport_sequence) & 0xFFFFFFFF
        if 0 < forward < 0x80000000:
            self.transport_missing += forward - 1
            self.last_transport_sequence = sequence
        elif forward != 0:
            self.transport_reordered += 1

    def _track_batch_sequence(self, sequence: int) -> None:
        if self.last_batch_sequence is None:
            self.last_batch_sequence = sequence
            return

        forward = (sequence - self.last_batch_sequence) & 0xFFFFFFFF
        if 0 < forward < 0x80000000:
            self.batch_missing += forward - 1
            self.last_batch_sequence = sequence
        elif forward != 0:
            self.batch_reordered += 1

    def _track_boot(self, boot_id: int) -> None:
        if self.receiver_boot_id is None:
            self.receiver_boot_id = boot_id
            return
        if boot_id == self.receiver_boot_id:
            return
        self.receiver_restarts += 1
        self.receiver_boot_id = boot_id
        self.last_transport_sequence = None
        self.last_batch_sequence = None

    def _ingest_packet(self, data: bytes) -> bool:
        host_receive_monotonic_ns = time.monotonic_ns()
        self.total_packets += 1
        try:
            packet = decode_csi_packet(data)
        except (CsiDatagramError, ValueError):
            self.malformed_lines += 1
            return False

        packet_receiver_mac = packet.records[0].receiver_mac
        if self.receiver_mac is None:
            self.receiver_mac = packet_receiver_mac
            self._status(f"locked to receiver {self.receiver_mac}", True)
        elif packet_receiver_mac != self.receiver_mac:
            self.foreign_packets += 1
            return False

        if self.profile_fingerprint:
            for decoded in packet.records:
                if (
                    decoded.record.profile_fingerprint != self.profile_fingerprint
                    and (
                        self.require_profile_fingerprint
                        or decoded.record.profile_fingerprint != ""
                    )
                ):
                    self.foreign_packets += 1
                    return False
        elif self.require_profile_fingerprint:
            if any(not decoded.record.profile_fingerprint for decoded in packet.records):
                self.foreign_packets += 1
                return False

        if packet.boot_id is not None:
            self._track_boot(packet.boot_id)
        if packet.batch_sequence is not None:
            self.batch_packets += 1
            self._track_batch_sequence(packet.batch_sequence)
        else:
            self.legacy_packets += 1
        if packet.receiver_stats is not None:
            self.receiver_stats = packet.receiver_stats

        for decoded in packet.records:
            self._track_transport_sequence(decoded.transport_sequence)
            record = decoded.record
            if self.profile_fingerprint and not record.profile_fingerprint:
                record = replace(record, profile_fingerprint=self.profile_fingerprint)
            # Each transmitted frame is captured about twice by the radio.  Keep
            # the first capture of a (sequence, tx timestamp) pair so a session
            # holds one row per sensing frame.  Rows without a transmit
            # timestamp (legacy/UDP transports) are never deduplicated.
            if record.tx_timestamp_us:
                # Include the receiver so two receivers observing the same
                # transmitted frame can never deduplicate each other, even if
                # this state were ever shared between readers.
                key = (record.receiver_mac, record.sequence, record.tx_timestamp_us)
                if key in self._recent_key_set:
                    self.duplicate_records += 1
                    continue
                if len(self._recent_keys) == self._recent_keys.maxlen:
                    self._recent_key_set.discard(self._recent_keys[0])
                self._recent_keys.append(key)
                self._recent_key_set.add(key)
            if self.record_sink is not None:
                self.record_sink(record, host_receive_monotonic_ns)
            else:
                if self._recorder is None:
                    self._recorder = CsiRecorder(self.output_dir)
                self._recorder.write_record(
                    record,
                    host_receive_monotonic_ns=host_receive_monotonic_ns,
                )
            self.buffer.append(record)
            self.last_valid_time = time.monotonic()
        if not self._stream_live:
            self._stream_live = True
            self._status(self.live_status, True)
        return True

    def _close_packet_stream(self) -> None:
        if self._recorder is not None:
            self._recorder.close()
            self._recorder = None
