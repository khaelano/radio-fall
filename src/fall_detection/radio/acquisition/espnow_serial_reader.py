"""Reconnectable reader for the ESP-NOW transmitter's serial gateway."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .buffer import RollingCsiBuffer
from .clock_sync import (
    ClockSyncError,
    ClockSyncEstimate,
    ClockSyncEstimator,
    ClockSyncSample,
    decode_clock_sync_sample,
)
from .packet_reader import BinaryCsiPacketReader
from .protocol import CsiRecord
from .recorder import ClockSyncRecorder
from .serial_framing import (
    TYPE_CSI_PACKET,
    TYPE_CLOCK_SYNC,
    TYPE_GATEWAY_STATS,
    TYPE_TRANSMITTER_STATS,
    SerialFrame,
    SerialFrameStreamDecoder,
)
from .telemetry import (
    GatewayTelemetry,
    TransmitterTelemetry,
    parse_gateway_telemetry,
    parse_transmitter_telemetry,
)


class EspNowSerialCsiReader(BinaryCsiPacketReader):
    """Read framed CSIB packets forwarded by the sensing transmitter."""

    def __init__(
        self,
        port: str,
        baud: int,
        buffer: RollingCsiBuffer,
        output_dir: Path,
        receiver_mac: Optional[str] = None,
        on_status: Optional[Callable[[str, bool], None]] = None,
        record_sink: Optional[Callable[[CsiRecord, int], None]] = None,
        clock_sync_sink: Optional[
            Callable[[ClockSyncSample, ClockSyncEstimate, int], None]
        ] = None,
    ) -> None:
        super().__init__(
            buffer,
            output_dir,
            receiver_mac=receiver_mac,
            on_status=on_status,
            live_status="ESP-NOW serial stream live",
            record_sink=record_sink,
        )
        self.port = port
        self.baud = baud
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._run, name="csi-espnow-serial-reader", daemon=True
        )
        self.transmitter_stats: Optional[TransmitterTelemetry] = None
        self.gateway_stats: Optional[GatewayTelemetry] = None
        self.clock_sync = ClockSyncEstimator()
        self.latest_clock_sync_sample: Optional[ClockSyncSample] = None
        self.clock_sync_frames = 0
        self.foreign_clock_sync_frames = 0
        self._clock_sync_recorder: Optional[ClockSyncRecorder] = None
        self.clock_sync_sink = clock_sync_sink
        self.serial_frames = 0

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)

    def _handle_telemetry(self, frame_type: int, payload: bytes) -> None:
        try:
            line = payload.decode("ascii")
            if frame_type == TYPE_TRANSMITTER_STATS:
                self.transmitter_stats = parse_transmitter_telemetry(line)
            else:
                self.gateway_stats = parse_gateway_telemetry(line)
        except (UnicodeDecodeError, ValueError):
            self.malformed_lines += 1

    def _handle_frame(self, frame: SerialFrame) -> None:
        self.serial_frames += 1
        if frame.type == TYPE_CSI_PACKET:
            self._ingest_packet(frame.payload)
        elif frame.type == TYPE_CLOCK_SYNC:
            try:
                sample = decode_clock_sync_sample(frame.payload)
                if self.receiver_mac is None:
                    self.receiver_mac = sample.receiver_mac
                    self._status(f"locked to receiver {self.receiver_mac}", True)
                elif sample.receiver_mac != self.receiver_mac:
                    self.foreign_clock_sync_frames += 1
                    return
                estimate = self.clock_sync.add(sample)
                self.latest_clock_sync_sample = sample
                self.clock_sync_frames += 1
                host_receive_monotonic_ns = time.monotonic_ns()
                if self.clock_sync_sink is not None:
                    self.clock_sync_sink(
                        sample, estimate, host_receive_monotonic_ns
                    )
                else:
                    if self._clock_sync_recorder is None:
                        self._clock_sync_recorder = ClockSyncRecorder(self.output_dir)
                    self._clock_sync_recorder.write(
                        sample,
                        estimate,
                        host_receive_monotonic_ns=host_receive_monotonic_ns,
                    )
            except ClockSyncError:
                self.malformed_lines += 1
        elif frame.type in (TYPE_TRANSMITTER_STATS, TYPE_GATEWAY_STATS):
            self._handle_telemetry(frame.type, frame.payload)

    def _run(self) -> None:
        try:
            import serial
            from serial import SerialException
        except ImportError:
            self._status("pyserial is not installed", False)
            return

        backoff = 0.5
        while not self.stop_event.is_set():
            decoder = SerialFrameStreamDecoder()
            try:
                self._status(f"opening ESP-NOW gateway: {self.port}", False)
                with serial.Serial(self.port, self.baud, timeout=0.25) as connection:
                    connection.dtr = False
                    connection.rts = False
                    self._status(
                        f"gateway open; waiting for CSI: {self.port}", True
                    )
                    backoff = 0.5
                    previous_malformed = 0
                    previous_oversized = 0
                    while not self.stop_event.is_set():
                        chunk = connection.read(max(1, connection.in_waiting))
                        if not chunk:
                            continue
                        frames = decoder.feed(chunk)
                        self.malformed_lines += (
                            decoder.malformed_frames - previous_malformed
                            + decoder.oversized_frames - previous_oversized
                        )
                        previous_malformed = decoder.malformed_frames
                        previous_oversized = decoder.oversized_frames
                        for frame in frames:
                            self._handle_frame(frame)
            except (SerialException, OSError) as exc:
                if self.stop_event.is_set():
                    break
                self._status(f"gateway serial error: {exc}; retrying", False)
            finally:
                self._close_packet_stream()

            if self.stop_event.is_set():
                break
            self._status("gateway disconnected; retrying", False)
            self.stop_event.wait(backoff)
            backoff = min(backoff * 2.0, 5.0)

    def _close_packet_stream(self) -> None:
        super()._close_packet_stream()
        if self._clock_sync_recorder is not None:
            self._clock_sync_recorder.close()
            self._clock_sync_recorder = None
