"""Transmitter commands, authoritative round logs and host clock mapping."""

from __future__ import annotations

import json
import struct
import time
from collections import deque
from collections.abc import Callable
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from typing import Any

from .clock_sync import ClockSyncEstimator, ClockSyncSample
from .serial_framing import (
    TYPE_GATEWAY_CONTROL,
    TYPE_GATEWAY_RESPONSE,
    TYPE_GATEWAY_ROUND,
    SerialFrameStreamDecoder,
    encode_serial_frame,
)

CONTROL_TYPE, RESPONSE_TYPE, ROUND_TYPE = (
    TYPE_GATEWAY_CONTROL,
    TYPE_GATEWAY_RESPONSE,
    TYPE_GATEWAY_ROUND,
)
ROUND = struct.Struct("!4sQIIQQIII3B")
# At most 1 MiB of raw USB chunks. This absorbs scheduling/journal stalls,
# while persistent consumer overload must still invalidate acquisition.
USB_READ_QUEUE_CHUNKS = 256


class TransmitterReference:
    """Own one reference stream; never infer capture time from gateway arrival."""

    def __init__(
        self,
        port: str,
        transmitter_mac: str,
        event_sink: Callable[..., None],
        *,
        expected_sensing_rate_hz: int,
        serial_factory: Callable[..., Any] | None = None,
        failure_sink: Callable[[str], None] | None = None,
        expected_profile_fingerprint: str | None = None,
        expected_sensing_phy: str | None = None,
        expected_sensing_version: int | None = None,
        minimum_clock_fit_span_us: int = 0,
    ) -> None:
        self.port = port
        self.mac = transmitter_mac
        self.event_sink = event_sink
        self.serial_factory = serial_factory
        self.failure_sink = failure_sink
        self.expected_profile_fingerprint = expected_profile_fingerprint
        self.expected_sensing_phy = expected_sensing_phy
        self.expected_sensing_version = expected_sensing_version
        if (
            type(expected_sensing_rate_hz) is not int
            or not 50 <= expected_sensing_rate_hz <= 120
        ):
            raise ValueError("unsupported expected sensing rate")
        self.expected_sensing_rate_hz = expected_sensing_rate_hz
        self.device_status = None
        self._status_ready = Event()
        self.estimator = ClockSyncEstimator(
            minimum_drift_span_us=minimum_clock_fit_span_us
        )
        self.connection = None
        self._stop = Event()
        self._responses = deque()
        self._response_ready = Event()
        self._write_lock = Lock()
        self._command_lock = Lock()
        self._thread = Thread(target=self._read, name="csi-tx-reference", daemon=True)
        self._usb_chunks: Queue[bytes] = Queue(maxsize=USB_READ_QUEUE_CHUNKS)
        self._usb_thread = Thread(
            target=self._drain_usb, name="csi-tx-usb-drain", daemon=True
        )
        self.usb_receive_queue_peak = 0
        self.last_round_time: float | None = None
        self.last_clock_time: float | None = None
        self.transmitter_boot_id: int | None = None
        self.run_id: int | None = None
        self.failure: str | None = None
        self.log_complete = True
        self.last_round: dict | None = None
        self._next_round = 0
        self._drop_baseline: int | None = None

    def start(self) -> None:
        """Open a transmitter without changing reset control lines."""
        if self.serial_factory is None:
            import serial

            self.serial_factory = serial.Serial
        self.connection = self.serial_factory(
            self.port, 921600, timeout=0.1, write_timeout=0.5, exclusive=True
        )
        self._usb_thread.start()
        self._thread.start()
        self.connection.write(encode_serial_frame(5, b""))
        if not self._status_ready.wait(2):
            raise TimeoutError("transmitter reference discovery timed out")
        status = self.device_status
        if (
            status.get("protocol_version") != 3
            or status.get("csi_transport") != "espnow_gateway"
            or status.get("role") != "transmitter"
            or status.get("mac") != self.mac
            or not status.get("ready")
            or (
                self.expected_profile_fingerprint is not None
                and status.get("profile_fingerprint")
                != self.expected_profile_fingerprint
            )
            or (
                self.expected_sensing_phy is not None
                and status.get("sensing_phy") not in (None, self.expected_sensing_phy)
            )
            or (
                self.expected_sensing_version is not None
                and status.get("sensing_version") != self.expected_sensing_version
            )
        ):
            raise RuntimeError(
                "transmitter identity/profile mismatch; provision the selected profile first"
            )

    def command(self, payload: bytes, timeout: float = 2.0) -> bytes:
        """Serialize commands and wait for the corresponding response."""
        with self._command_lock:
            self._responses.clear()
            self._response_ready.clear()
            with self._write_lock:
                self.connection.write(encode_serial_frame(CONTROL_TYPE, payload))
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if self.failure:
                    raise RuntimeError(self.failure)
                if self._response_ready.wait(
                    min(0.1, max(0, deadline - time.monotonic()))
                ):
                    self._response_ready.clear()
                    if self._responses:
                        response = self._responses.popleft()
                        if payload[:4] == b"CGHC":
                            if len(response) != 40 or response[:16] != payload:
                                continue
                        elif response not in (b"ok", b"error"):
                            continue
                        if response == b"error":
                            raise RuntimeError("transmitter rejected gateway command")
                        return response
            raise TimeoutError("transmitter command timed out")

    def sync(self, sync_id: int) -> None:
        """Record one symmetric reference exchange and update its affine fit."""
        t1 = time.monotonic_ns() // 1000
        response = self.command(struct.pack("!4sIQ", b"CGHC", sync_id, t1))
        t4 = time.monotonic_ns() // 1000
        _, identity, echoed, t2, t3, boot, drops = struct.unpack("!4sIQQQII", response)
        if self._drop_baseline is None:
            self._drop_baseline = drops
        if drops != self._drop_baseline:
            self.log_complete = False
            self._fail("transmitter reference log is incomplete")
            raise RuntimeError(self.failure)
        self._check_boot(boot)
        sample = ClockSyncSample(identity, 0, boot, echoed, t2, t3, t4, 0, 0, self.mac)
        estimate = self.estimator.add(sample)
        self.last_clock_time = time.monotonic()
        self.event_sink(
            "clock_exchange",
            sample=sample.__dict__,
            estimate=estimate.__dict__ if estimate else None,
            lifetime_log_drops=drops,
            prior_run_log_drops=self._drop_baseline,
        )

    def _check_boot(self, boot: int) -> None:
        if self.transmitter_boot_id is not None and boot != self.transmitter_boot_id:
            self._fail("transmitter restarted; start a new run")
            raise RuntimeError(self.failure)
        self.transmitter_boot_id = boot

    @property
    def ready(self) -> bool:
        """Require a fresh reference and a fitted host/device clock."""
        return (
            not self.failure
            and self.log_complete
            and self.estimator.estimate is not None
            and self.last_clock_time is not None
            and time.monotonic() - self.last_clock_time < 3
        )

    def capture_time(self, transmitter_us: int) -> int | None:
        """Map an enqueue timestamp, keeping unavailable alignment explicit."""
        if not self.ready:
            return None
        return round(
            self.estimator.estimate.receiver_to_transmitter(transmitter_us) * 1000
        )

    @property
    def usb_backlog_chunks(self) -> int:
        """Return queued read chunks, independently of firmware record queues."""
        return self._usb_chunks.qsize()

    def _fail(self, message: str) -> None:
        if self.failure is not None:
            return
        self.failure = message
        if self.failure_sink:
            self.failure_sink(message)

    def _drain_usb(self) -> None:
        """Drain USB independently of decoding, journals and radio bookkeeping."""
        try:
            while not self._stop.is_set() and not self.failure:
                chunk = self.connection.read(
                    max(1, min(4096, getattr(self.connection, "in_waiting", 1)))
                )
                if not chunk:
                    continue
                try:
                    self._usb_chunks.put_nowait(chunk)
                except Full:
                    self.log_complete = False
                    self._fail("transmitter USB receive queue overflow")
                    return
                self.usb_receive_queue_peak = max(
                    self.usb_receive_queue_peak, self._usb_chunks.qsize()
                )
        except Exception as exc:  # noqa: BLE001 — acquisition thread boundary
            if not self._stop.is_set():
                self._fail(f"transmitter reference lost: {exc}")

    def _read(self) -> None:
        decoder = SerialFrameStreamDecoder()
        last_errors = (0, 0)
        try:
            while not self._stop.is_set() and not self.failure:
                try:
                    chunk = self._usb_chunks.get(timeout=0.1)
                except Empty:
                    continue
                decoded = decoder.feed(chunk)
                errors = (decoder.malformed_frames, decoder.oversized_frames)
                if errors != last_errors:
                    if self._status_ready.is_set():
                        self.log_complete = False
                        self._fail("transmitter reference framing error")
                        return
                    self.event_sink(
                        "preflight_usb_discard",
                        malformed=errors[0],
                        oversized=errors[1],
                    )
                    last_errors = errors
                for frame in decoded:
                    if self.failure or self._stop.is_set():
                        return
                    if frame.type == 6:
                        self.device_status = json.loads(frame.payload)
                        self._status_ready.set()
                    elif frame.type == RESPONSE_TYPE:
                        self._responses.append(frame.payload)
                        self._response_ready.set()
                    elif frame.type == 23:
                        payload = frame.payload
                        offset = (
                            8
                            if payload[:4] in (b"CGST", b"CGCK", b"CGQE", b"CGMT")
                            else 4
                        )
                        stale = (
                            self.run_id is not None
                            and len(payload) >= offset + 8
                            and struct.unpack_from("!Q", payload, offset)[0]
                            != self.run_id
                        )
                        self.event_sink(
                            "stale_radio_event" if stale else "radio_event",
                            payload_hex=payload.hex(),
                        )
                    elif frame.type == ROUND_TYPE:
                        self.accept_round(frame.payload)
        except Exception as exc:  # noqa: BLE001 — acquisition thread boundary
            if not self._stop.is_set():
                self._fail(f"transmitter reference lost: {exc}")

    def accept_round(self, payload: bytes) -> None:
        """Validate and record an authoritative CGRD transmitter event."""
        if len(payload) != ROUND.size:
            raise ValueError("invalid transmitter round log size")
        magic, run, boot, seq, enqueue, deadline, period, result, drops, *owners = (
            ROUND.unpack(payload)
        )
        if magic != b"CGRD":
            raise ValueError("invalid transmitter round log")
        if period != 1_000_000 // self.expected_sensing_rate_hz:
            raise ValueError("transmitter round period differs from configured rate")
        if self.run_id is not None and run != self.run_id:
            return
        self._check_boot(boot)
        if seq != self._next_round:
            self.log_complete = False
            self.event_sink(
                "transmitter_round_rejected",
                reason="sequence_gap",
                expected_sequence=self._next_round,
                received_sequence=seq,
                run_id=run,
                transmitter_boot_id=boot,
                lifetime_log_drops=drops,
                prior_run_log_drops=self._drop_baseline,
                payload_hex=payload.hex(),
            )
            self._fail("transmitter round log has an unexplained sequence gap")
            raise RuntimeError(self.failure)
        step = (result & 0x7FFFFFFF) if result & 0x80000000 else 1
        if step < 1:
            raise ValueError("invalid skipped-round count")
        self._next_round = (seq + step) & 0xFFFFFFFF
        self.last_round_time = time.monotonic()
        if self._drop_baseline is None:
            self._drop_baseline = drops
        if drops != self._drop_baseline:
            self.log_complete = False
            self.event_sink(
                "transmitter_log_loss",
                sequence=seq,
                lifetime_log_drops=drops,
                prior_run_log_drops=self._drop_baseline,
                payload_hex=payload.hex(),
            )
            self._fail("transmitter reference round log overflow")
        value = {
            "run_id": run,
            "transmitter_boot_id": boot,
            "sequence": seq,
            "tx_enqueue_us": enqueue,
            "scheduled_us": deadline,
            "period_us": period,
            "send_mask": result & 0xF,
            "skipped_rounds": result & 0x7FFFFFFF if result & 0x80000000 else 0,
            "log_drops": (drops - self._drop_baseline) & 0xFFFFFFFF,
            "lifetime_log_drops": drops,
            "owners": owners,
            "host_capture_ns": self.capture_time(enqueue),
        }
        self.last_round = value
        self.event_sink("round", **value)

    def stop(self) -> None:
        """Close only this reference connection."""
        self._stop.set()
        if self.connection:
            self.connection.close()
        if self._thread.is_alive():
            self._thread.join(timeout=2)
        if self._usb_thread.is_alive():
            self._usb_thread.join(timeout=2)
