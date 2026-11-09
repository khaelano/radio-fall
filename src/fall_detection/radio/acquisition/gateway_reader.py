"""Scheduled dual-band acquisition through a dedicated C6 USB gateway."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
import os
import secrets
import struct
from threading import Event, Lock, Thread
from typing import Any, Callable
import time

from ..espnow_config import EspnowTransportConfig, CONTROL, RESPONSE, ENVELOPE, ACK
from ..profile import RadioInventory, RadioProfile, profile_fingerprint
from .availability import AvailabilityGrid, RoundReceipts
from .buffer import RollingCsiBuffer
from .gateway_journal import GatewayJournal
from .gateway_protocol import GatewayBatch, checked
from .gateway_diagnostics import DeliveryRates, GatewayDiagnostics, ReceiverDiagnostics
from .packet_reader import BinaryCsiPacketReader
from .recorder import CsiRecorder
from .protocol import CsiRecord
from .clock_sync import ClockSyncEstimator
from .serial_framing import SerialFrameStreamDecoder, encode_serial_frame
from .telemetry import BackhaulTelemetrySnapshot
from .transmitter_reference import TransmitterReference
from .usb_buffer import UsbReadBuffer
from .wireless_reference import WirelessReferenceSerial


# Yield optional plots well before the independent 200 ms ingestion deadline.
PREVIEW_MAX_QUEUED_CHUNKS = 8
PREVIEW_MAX_QUEUE_AGE_NS = 25_000_000


@dataclass(frozen=True)
class GatewayBinding:
    """A configured receiver slot; USB port belongs to the shared gateway."""

    receiver_id: str
    mac: str
    target: str
    port: str
    profile_fingerprint: str


class GatewayReceiverState(BinaryCsiPacketReader):
    """Independent decoder and health state for one registered physical receiver."""

    def __init__(
        self,
        binding: GatewayBinding,
        profile: RadioProfile,
        output_dir: Path,
        record_sink: Callable[[CsiRecord, int], None],
        on_status: Callable[[str, bool], None] | None,
    ) -> None:
        super().__init__(
            RollingCsiBuffer(nominal_rate=profile.nominal_rate_hz, seconds=10),
            output_dir,
            receiver_mac=binding.mac,
            record_sink=record_sink,
            on_status=on_status,
            profile_fingerprint=binding.profile_fingerprint,
            require_profile_fingerprint=True,
        )
        self.binding = binding
        self.status = {}
        self.connected = False
        self.profile_mismatch = False


class GatewayReceiverManager:
    """Coordinate gateway/reference links, recorder acceptance and availability.

    Factories are injectable for deterministic offline tests. Hardware startup
    requires explicitly named USB ports; receiver slot order is never discovered.
    """

    def __init__(
        self,
        inventory: RadioInventory,
        profile: RadioProfile,
        output_dir: Path,
        *,
        transmitter_port: str | None,
        gateway_port: str,
        transmitter_link: str = "usb",
        config: EspnowTransportConfig | None = None,
        require_four: bool = False,
        on_status: Callable[[str, bool], None] | None = None,
        record_sink: Callable[[CsiRecord, int], None] | None = None,
        journal_root: Path | Callable[[], Path | None] | None = None,
        reference_failure_sink: Callable[[str], None] | None = None,
        serial_factory: Callable[..., Any] | None = None,
        reference_factory: Callable[..., Any] | None = None,
        run_id: int | None = None,
        recovery_context: dict[str, Any] | None = None,
        recording_io=None,
    ) -> None:
        self.inventory, self.profile, self.output_dir = inventory, profile, output_dir
        self.transmitter_port, self.gateway_port = transmitter_port, gateway_port
        if transmitter_link not in {"usb", "ble", "espnow_uart"}:
            raise ValueError("unsupported transmitter link")
        self.transmitter_link = transmitter_link
        self._wireless_prefix = (
            "relay" if transmitter_link == "espnow_uart" else "wireless"
        )
        self._wireless_serial = None
        self._wireless_peer_baseline = None
        self._wireless_drop_baseline = None
        self._reference_pending = deque()
        self.config = config or EspnowTransportConfig()
        self.require_four = require_four
        self.on_status, self.record_sink = on_status, record_sink
        self.journal_root, self.reference_failure_sink = (
            journal_root,
            reference_failure_sink,
        )
        self.serial_factory, self.reference_factory = (
            serial_factory,
            reference_factory or TransmitterReference,
        )
        self.run_id = run_id or secrets.randbits(64) or 1
        self.recovery_context = recovery_context
        self.recording_io = recording_io
        self.expected_fingerprint = profile_fingerprint(profile, inventory)
        self.bindings, self.readers = {}, {}
        self.reference = self.journal = self.grid = self.receipts = self.connection = (
            None
        )
        self.gateway_status = {}
        self._gateway_status_ns = None
        self._delivery_rates = DeliveryRates()
        self.failure = None
        self._stop, self._status_ready, self._response_ready = Event(), Event(), Event()
        self._usb_stop = Event()
        self._write_lock, self._command_lock = Lock(), Lock()
        self._responses = deque(maxlen=16)
        self._thread = Thread(target=self._run, name="csi-gateway", daemon=True)
        self._usb_thread = None
        self._usb_drain_thread = None
        self._native_pipeline = None
        self._usb_drain_done = Event()
        self._usb_buffer = UsbReadBuffer()
        self._shutdown_error = None
        self._recording_shutdown_error = None
        self._accepting = False
        self._recorders = {}
        self._fallback_buffer = RollingCsiBuffer(nominal_rate=profile.nominal_rate_hz)
        self._accepted = set()
        self._accepted_order = deque()
        self._receiver_heartbeats = {}
        self._receiver_clocks = {}
        self._intervals = set()
        self._interval_order = deque()

    def bind(self) -> tuple[GatewayBinding, ...]:
        """Validate targets, fixed identities and policy before touching hardware."""
        self.config.validate(
            self.inventory, self.profile, require_four=self.require_four
        )
        if (
            (self.transmitter_link == "usb" and not self.transmitter_port)
            or not self.gateway_port
            or (
                self.transmitter_link == "usb"
                and self.transmitter_port == self.gateway_port
            )
        ):
            raise ValueError("distinct --port and --gateway-port are required")
        for device in self.inventory.receivers:
            binding = GatewayBinding(
                device.id,
                device.mac,
                device.target,
                self.gateway_port,
                self.expected_fingerprint,
            )
            self.bindings[device.id] = binding
            self.readers[device.id] = GatewayReceiverState(
                binding,
                self.profile,
                self.output_dir / device.id,
                self._record,
                self.on_status,
            )
        return tuple(self.bindings.values())

    def _fail(self, message: str) -> None:
        if self.failure is not None:
            return
        self.failure = message
        if self.journal:
            try:
                self.journal.event("run_interrupted", reason=message)
            except OSError as exc:
                self.failure = message = f"journal could not record interruption: {exc}"
        self._status_ready.set()
        self._response_ready.set()
        if self.on_status:
            self.on_status(message, False)
        if self.reference_failure_sink:
            self.reference_failure_sink(message)

    def _event(self, kind: str, **values) -> None:
        if self.journal:
            self.journal.event(kind, **values)
        if kind == "round" and self.receipts:
            self.receipts.round(values)
        if kind == "radio_event":
            data = bytes.fromhex(values["payload_hex"])
            if data[:4] == b"CGST":
                checked(data, b"CGST", 96)
                slot = data[5]
                if (
                    slot >= len(self.inventory.receivers)
                    or struct.unpack_from("!Q", data, 8)[0] != self.run_id
                ):
                    raise ValueError("receiver status run/slot mismatch")
                state = self.readers[self.inventory.receivers[slot].id]
                boot = struct.unpack_from("!I", data, 20)[0]
                if state.status.get("boot_id", boot) != boot:
                    raise RuntimeError("receiver restarted; start a new run")
                state.status = dict(
                    boot_id=boot,
                    state=data[6],
                    grant=struct.unpack_from("!I", data, 24)[0],
                    captured=struct.unpack_from("!I", data, 72)[0],
                    dropped=struct.unpack_from("!I", data, 76)[0],
                    expired=struct.unpack_from("!I", data, 80)[0],
                    queued=struct.unpack_from("!H", data, 84)[0],
                    departed_us=struct.unpack_from("!Q", data, 56)[0],
                    returned_us=struct.unpack_from("!Q", data, 64)[0],
                    transition_grant=struct.unpack_from("!I", data, 28)[0],
                    peak=struct.unpack_from("!H", data, 86)[0],
                    queue_event_loss=bool(data[7]),
                    send_errors=struct.unpack_from("!I", data, 88)[0],
                )
                state.connected = True
                self._receiver_heartbeats[state.binding.receiver_id] = time.monotonic()
                self.journal.event(
                    "receiver_status",
                    receiver_id=state.binding.receiver_id,
                    **state.status,
                )
                self._interval(state)
            elif data[:4] == b"CGMT":
                checked(data, b"CGMT", 64)
                slot = data[5]
                if (
                    slot >= len(self.inventory.receivers)
                    or struct.unpack_from("!Q", data, 8)[0] != self.run_id
                ):
                    raise ValueError("MAC metric run/slot mismatch")
                self.journal.event(
                    "mac_completion_summary",
                    receiver_id=self.inventory.receivers[slot].id,
                    receiver_boot_id=struct.unpack_from("!I", data, 20)[0],
                    grant_id=struct.unpack_from("!I", data, 24)[0],
                    samples=struct.unpack_from("!H", data, 28)[0],
                    failures=struct.unpack_from("!H", data, 30)[0],
                    minimum_us=struct.unpack_from("!I", data, 32)[0],
                    maximum_us=struct.unpack_from("!I", data, 36)[0],
                    total_us=struct.unpack_from("!Q", data, 40)[0],
                    maximum_failure_us=struct.unpack_from("!I", data, 48)[0],
                    completions_after_cutoff=struct.unpack_from("!I", data, 52)[0],
                    sender_busy_at_return=bool(data[6]),
                )
            elif data[:4] == b"CGQE":
                checked(data, b"CGQE", 48)
                slot = data[5]
                if (
                    slot >= len(self.inventory.receivers)
                    or struct.unpack_from("!Q", data, 8)[0] != self.run_id
                ):
                    raise ValueError("queue event run/slot mismatch")
                self.journal.event(
                    "queue_event",
                    receiver_id=self.inventory.receivers[slot].id,
                    event_code=data[6],
                    records=data[7],
                    batch_id=struct.unpack_from("!I", data, 24)[0],
                    grant_id=struct.unpack_from("!I", data, 28)[0],
                    receiver_timestamp_us=struct.unpack_from("!Q", data, 32)[0],
                    queued=struct.unpack_from("!H", data, 40)[0],
                    attempts=data[42],
                    detail=data[43],
                )
            elif data[:4] == b"CGCK":
                checked(data, b"CGCK", 60)
                slot = data[5]
                a, b, c, d = struct.unpack_from("!4Q", data, 24)
                if (
                    0 <= slot < len(self.inventory.receivers)
                    and 0 <= (d - a) - (c - b) <= 8000
                ):
                    boot = struct.unpack_from("!I", data, 20)[0]
                    self._receiver_clocks[slot, boot] = (a - b, d - c, c)
                    self._interval(self.readers[self.inventory.receivers[slot].id])

    def _interval(self, state) -> None:
        """Journal conservative off-channel bounds, including clock uncertainty."""
        s = state.status
        slot = next(
            i
            for i, d in enumerate(self.inventory.receivers)
            if d.mac == state.receiver_mac
        )
        clock = self._receiver_clocks.get((slot, s.get("boot_id")))
        departed, returned = s.get("departed_us", 0), s.get("returned_us", 0)
        key = (slot, s.get("boot_id"), s.get("transition_grant"))
        if not clock or not departed or returned <= departed or key in self._intervals:
            return
        lower, upper, sampled = clock
        drift = max(abs(departed - sampled), abs(returned - sampled)) / 1000 + 250
        mapping = self.reference.capture_time
        values = [
            mapping(departed + lower - drift),
            mapping(departed + upper + drift),
            mapping(returned + lower - drift),
            mapping(returned + upper + drift),
        ]
        if any(v is None for v in values):
            return
        uncertainty = self.reference.estimator.estimate.uncertainty_us * 1000
        self.journal.event(
            "channel_interval",
            receiver_id=state.binding.receiver_id,
            receiver_boot_id=s["boot_id"],
            grant_id=s["transition_grant"],
            start_lower_ns=values[0] - uncertainty,
            start_upper_ns=values[1] + uncertainty,
            end_lower_ns=values[2] - uncertainty,
            end_upper_ns=values[3] + uncertainty,
        )
        if len(self._interval_order) >= 4096:
            self._intervals.discard(self._interval_order.popleft())
        self._interval_order.append(key)
        self._intervals.add(key)

    def _record(self, record, arrival_ns: int) -> None:
        receiver_id = next(
            d.id for d in self.inventory.receivers if d.mac == record.receiver_mac
        )
        if record.capture_host_monotonic_ns is None:
            raise RuntimeError("capture clock alignment unavailable")
        if self.record_sink:
            self.record_sink(record, arrival_ns)
        else:
            recorder = self._recorders.setdefault(receiver_id, None)
            if recorder is None:
                recorder = self._recorders[receiver_id] = CsiRecorder(
                    self.output_dir / receiver_id, recording_io=self.recording_io
                )
            recorder.write_record(record, host_receive_monotonic_ns=arrival_ns)
        accepted = time.monotonic_ns()
        timely = self.grid.observe(
            receiver_id, record.capture_host_monotonic_ns, accepted
        )
        self.receipts.receive(
            record.transmitter_boot_id, record.sequence, receiver_id, accepted
        )
        self.journal.event(
            "record",
            receiver_id=receiver_id,
            sequence=record.sequence,
            receiver_boot_id=record.receiver_boot_id,
            transmitter_boot_id=record.transmitter_boot_id,
            capture_host_ns=record.capture_host_monotonic_ns,
            arrival_ns=arrival_ns,
            available_ns=accepted,
            clock_uncertainty_us=record.capture_clock_uncertainty_us,
            timely=timely,
            tx_enqueue_us=record.tx_timestamp_us,
            rx_callback_us=record.rx_callback_timestamp_us,
            rx_radio_us=record.timestamp_us,
            native_processing_completed_ns=getattr(record, "native_processed_ns", None),
        )

    def accept(self, data: bytes, arrival_ns: int) -> bool:
        """Validate and record atomically at the application level before ACK."""
        return self._accept_batch(GatewayBatch.decode(data), arrival_ns)

    def _accept_batch(self, batch: GatewayBatch, arrival_ns: int) -> bool:
        """Accept an already wire-validated envelope with all live-session checks."""
        if batch.run_id != self.run_id:
            return False
        if not self.reference or not self.reference.ready:
            raise RuntimeError("transmitter reference unavailable")
        if batch.transmitter_boot_id != self.reference.transmitter_boot_id:
            raise ValueError("gateway transmitter boot mismatch")
        state = next(
            (s for s in self.readers.values() if s.receiver_mac == batch.receiver_mac),
            None,
        )
        if state is None or batch.receiver_boot_id != state.status.get("boot_id"):
            raise ValueError("receiver identity/boot not verified")
        packet = batch.decoded_packet
        if any(
            r.record.profile_fingerprint != self.expected_fingerprint
            for r in packet.records
        ):
            raise ValueError("gateway sensing profile mismatch")
        self.journal.accept(batch, arrival_ns)
        if batch.identity not in self._accepted:
            before_records = state.buffer.received_records
            if not state.ingest_decoded_packet(
                packet,
                host_receive_monotonic_ns=arrival_ns,
                context=dict(
                    run_id=batch.run_id,
                    transmitter_boot_id=batch.transmitter_boot_id,
                    receiver_boot_id=batch.receiver_boot_id,
                    transport="espnow_gateway",
                    capture_clock_uncertainty_us=self.reference.estimator.estimate.uncertainty_us,
                ),
                capture_clock=self.reference.capture_time,
            ):
                raise ValueError("CSI decoder rejected batch")
            self._delivery_rates.observe(
                state.binding.receiver_id,
                state.buffer.received_records - before_records,
                time.monotonic_ns(),
            )
            self._accepted.add(batch.identity)
            self._accepted_order.append(batch.identity)
            if len(self._accepted_order) > 4096:
                self._accepted.discard(self._accepted_order.popleft())
        if self.config.application_acknowledgements:
            if self.recording_io:
                self.recording_io.flush()
            acknowledgement = batch.acknowledgement()
            self._write(ACK, acknowledgement)
            self.journal.event(
                "host_acceptance_ack",
                receiver_id=state.binding.receiver_id,
                batch_id=batch.batch_id,
                receiver_boot_id=batch.receiver_boot_id,
                payload_hex=acknowledgement.hex(),
            )
        else:
            self.journal.event(
                "host_acceptance",
                receiver_id=state.binding.receiver_id,
                batch_id=batch.batch_id,
                receiver_boot_id=batch.receiver_boot_id,
                acknowledgement_sent=False,
            )
        return True

    def _write(self, kind: int, payload: bytes) -> None:
        data = encode_serial_frame(kind, payload)
        with self._write_lock:
            if self.connection.write(data) != len(data):
                raise OSError("short gateway USB write")

    def _command(self, payload: bytes, timeout: float = 2) -> None:
        with self._command_lock:
            self._responses.clear()
            self._response_ready.clear()
            self._write(CONTROL, payload)
            self._response_ready.wait(timeout)
            if self.failure:
                raise RuntimeError(self.failure)
            if not self._responses:
                raise TimeoutError("gateway command timed out")
            if self._responses.popleft() != b"ok":
                raise RuntimeError("gateway rejected configuration/control")

    def _drain_gateway_usb(self) -> None:
        """Own USB reads; leave validation, recording and ACKs to the worker."""
        try:
            while not self._usb_stop.is_set() and not self.failure:
                # Bulk reads coalesce USB packet fragments. The 5 ms serial
                # timeout bounds aggregation; processing never waits for a
                # full group. Timestamp the completed read, not later decoding.
                data = self.connection.read(4096)
                arrival = time.monotonic_ns()
                if data:
                    self._usb_buffer.put(data, arrival)
        except Exception as exc:
            if self._usb_stop.is_set():
                self._shutdown_error = f"gateway USB shutdown failed to drain: {exc}"
                self._fail(self._shutdown_error)
            else:
                self._fail(f"gateway USB receive failed: {exc}")
        finally:
            self._usb_drain_done.set()
            self._usb_buffer.close()

    def _read_usb(self) -> None:
        """Process bounded groups of already available reads in wire order."""
        import json

        decoder = SerialFrameStreamDecoder()
        last_errors = (0, 0)
        try:
            while not self.failure:
                native_done = False
                if self._native_pipeline is not None:
                    values = self._native_pipeline.frames()
                    state = self._usb_buffer.stats()
                    native_done = state["done"] and not values
                    frames = [(f.arrival_ns, f) for f in values]
                    decoder.malformed_frames = state["malformed_frames"]
                    decoder.oversized_frames = state["oversized_frames"]
                else:
                    chunks = self._usb_buffer.get_batch(max_chunks=4)
                    if not chunks:
                        if self._usb_drain_done.is_set():
                            break
                        continue
                    frames = []
                    for chunk in chunks:
                        if (
                            time.monotonic_ns() - chunk.arrival_ns
                            > self._usb_buffer.maximum_age_ns
                        ):
                            raise TimeoutError("gateway USB receive buffer age exceeded")
                        frames.extend(
                            (chunk.arrival_ns, frame) for frame in decoder.feed(chunk.data)
                        )
                for arrival, frame in frames:
                    if self.failure:
                        return
                    if frame.type == 6:
                        status = json.loads(frame.payload)
                        gateway = self.inventory.gateway
                        if (
                            status.get("role"),
                            status.get("target"),
                            status.get("mac"),
                            status.get("protocol_version"),
                            status.get("csi_transport"),
                        ) != ("gateway", "esp32c6", gateway.mac, 3, "espnow_gateway"):
                            raise ValueError("gateway firmware/identity mismatch")
                        if self.gateway_status and self.gateway_status.get(
                            "boot_id"
                        ) != status.get("boot_id"):
                            raise RuntimeError("gateway restarted; start a new run")
                        self.gateway_status = status
                        self._gateway_status_ns = arrival
                        if self._wireless_drop_baseline is None:
                            self._wireless_drop_baseline = status.get(
                                f"{self._wireless_prefix}_drops", 0
                            )
                        if self._wireless_peer_baseline is None or not self._accepting:
                            self._wireless_peer_baseline = status.get(
                                f"{self._wireless_prefix}_peer_changes", 0
                            )
                        if self.transmitter_link != "usb" and (
                            status.get(f"{self._wireless_prefix}_fault")
                            or status.get(f"{self._wireless_prefix}_drops", 0)
                            != self._wireless_drop_baseline
                            or status.get(f"{self._wireless_prefix}_peer_changes", 0)
                            != self._wireless_peer_baseline
                        ):
                            if self.journal:
                                self.journal.event("wireless_reference_fault", **status)
                            raise RuntimeError(
                                "wireless transmitter reference failed: "
                                + status.get(
                                    f"{self._wireless_prefix}_failure_reason", "unknown"
                                )
                                + "; restart both bridge endpoints"
                            )
                        self._status_ready.set()
                        if self.journal:
                            self.journal.event(
                                "gateway_status", usb_read_ns=arrival, **status
                            )
                    elif frame.type == RESPONSE:
                        self._responses.append(frame.payload)
                        self._response_ready.set()
                    elif frame.type == ENVELOPE:
                        payload = frame.payload
                        if self._native_pipeline is not None:
                            from .native import gateway_batch

                            batch = gateway_batch(frame.batch, frame.processed_ns, payload)
                        else:
                            batch = None
                        if self.transmitter_link != "usb":
                            if len(self._reference_pending) >= 128:
                                raise BufferError(
                                    "wireless reference envelope queue overflow"
                                )
                            batch = batch or GatewayBatch.decode(payload)
                            if batch.run_id == self.run_id:
                                self._reference_pending.append(
                                    (arrival, payload, batch)
                                )
                        else:
                            if batch is not None:
                                self._accept_batch(batch, arrival)
                            else:
                                self.accept(payload, arrival)
                    elif frame.type == 27 and self._wireless_serial:
                        self._wireless_serial.feed(frame.payload)
                self._flush_reference_pending()
                errors = (decoder.malformed_frames, decoder.oversized_frames)
                if errors != last_errors:
                    if self._accepting:
                        raise ValueError("gateway USB framing error")
                    self.journal.event(
                        "preflight_usb_discard",
                        malformed=errors[0],
                        oversized=errors[1],
                    )
                    last_errors = errors
                if native_done:
                    break
        except Exception as exc:
            if not self._stop.is_set():
                self._fail(f"gateway ingestion failed: {exc}")

    def _flush_reference_pending(self) -> None:
        """Wait briefly for BLE status without substituting arrival timestamps."""
        while self._reference_pending:
            arrival, _payload, batch = self._reference_pending[0]
            state = next(
                (
                    s
                    for s in self.readers.values()
                    if s.receiver_mac == batch.receiver_mac
                ),
                None,
            )
            if state is None:
                raise ValueError("unregistered wireless CSI receiver")
            if state.status.get("boot_id") != batch.receiver_boot_id:
                if time.monotonic_ns() - arrival > 750_000_000:
                    raise TimeoutError("wireless receiver boot evidence unavailable")
                return
            self._accept_batch(batch, arrival)
            self._reference_pending.popleft()

    def _run(self) -> None:
        owned_io = False
        try:
            if self.recording_io is None:
                from .recording_io import RecordingIO

                self.recording_io = RecordingIO()
                owned_io = True
            if not self.readers:
                self.bind()
            root = (
                self.journal_root()
                if callable(self.journal_root)
                else self.journal_root
            )
            root = root or self.output_dir / f"gateway-{self.run_id:016x}"
            from .native import backend_info

            self.journal = GatewayJournal(
                root,
                self.run_id,
                dict(
                    host_processing=backend_info(),
                    transport="espnow_gateway",
                    transmitter_link=self.transmitter_link,
                    host_clock_minimum_drift_span_us=10_000_000
                    if self.transmitter_link != "usb"
                    else 0,
                    host_usb_buffer=dict(
                        reader_isolation="rust"
                        if os.name == "posix" and self.serial_factory is None
                        else "thread",
                        reader_process_fifo_bytes=0,
                        capacity_bytes=self._usb_buffer.capacity_bytes,
                        capacity_chunks=self._usb_buffer.capacity_chunks,
                        maximum_age_ns=self._usb_buffer.maximum_age_ns,
                        processing_group_max_chunks=8
                        if os.name == "posix" and self.serial_factory is None else 4,
                        native_decoder_workers=2,
                        native_completed_capacity_bytes=16 * 1024 * 1024,
                        maximum_read_bytes=4096,
                        read_timeout_ms=5,
                    ),
                    transport_config=asdict(self.config),
                    transport_fingerprint=self.config.fingerprint(
                        self.inventory, self.profile
                    ),
                    inventory=self.inventory.as_dict(),
                    profile=self.profile.as_dict(),
                    recovery=self.recovery_context,
                ),
                recording_io=self.recording_io,
            )
            if self.recovery_context:
                self.journal.event("run_resuming", **self.recovery_context)
            if self.transmitter_link != "usb":
                self._open_gateway()
                expected_version = 1 if self.transmitter_link == "espnow_uart" else 2
                if self.gateway_status.get(
                    f"{self._wireless_prefix}_version"
                ) != expected_version or not self.gateway_status.get(
                    f"{self._wireless_prefix}_paired"
                ):
                    raise RuntimeError(
                        "gateway lacks a paired connectionless transmitter bridge for the selected link"
                    )
                if (
                    self.transmitter_link == "espnow_uart"
                    and self.gateway_status.get("relay_transport") != "espnow_uart"
                ):
                    raise RuntimeError("gateway relay transport mismatch")
                deadline = time.monotonic() + 8
                while (
                    not self.gateway_status.get(f"{self._wireless_prefix}_ready")
                    and not self.failure
                    and time.monotonic() < deadline
                ):
                    if self._stop.wait(0.05):
                        return
                if self.failure or not self.gateway_status.get(
                    f"{self._wireless_prefix}_ready"
                ):
                    raise RuntimeError(
                        self.failure or "wireless reference handshake timed out"
                    )
                self._wireless_serial = WirelessReferenceSerial(self._write)
            reference_options = {}
            if self._wireless_serial:
                reference_options["minimum_clock_fit_span_us"] = 10_000_000
                reference_options["serial_factory"] = lambda *a, **k: (
                    self._wireless_serial
                )
            self.reference = self.reference_factory(
                self.transmitter_port or f"{self.transmitter_link}-via-gateway",
                self.inventory.transmitter.mac,
                self._event,
                failure_sink=self._fail,
                expected_profile_fingerprint=self.expected_fingerprint,
                expected_sensing_phy="he20",
                expected_sensing_version=4,
                expected_sensing_rate_hz=self.profile.nominal_rate_hz,
                **reference_options,
            )
            self.reference.run_id = self.run_id
            self.reference.start()
            if (
                self.config.schema_version >= 5
                and self.reference.device_status.get("transport_config_max_version", 0)
                < self.config.schema_version
            ):
                raise RuntimeError(
                    "transmitter firmware lacks requested transport version"
                )
            for i in range(8):
                self.reference.sync(i)
                if self._stop.wait(0.02):
                    return
            if not self.reference.ready:
                raise RuntimeError("transmitter clock fit unavailable")
            if not self.connection:
                self._open_gateway()
            if self.failure:
                raise RuntimeError(self.failure)
            if (
                self.config.schema_version >= 5
                and self.gateway_status.get("transport_config_max_version", 0)
                < self.config.schema_version
            ):
                raise RuntimeError("gateway firmware lacks requested transport version")
            if self.gateway_status.get("configured"):
                previous_run = int(self.gateway_status["run_id"])
                self._command(struct.pack("!4sQ", b"CGSP", previous_run))
            config = self.config.encode(self.run_id, self.inventory, self.profile)
            self._command(config)
            self._command(
                struct.pack(
                    "!4sQI", b"CGTB", self.run_id, self.reference.transmitter_boot_id
                )
            )
            self.grid = AvailabilityGrid(
                tuple(self.readers),
                time.monotonic_ns(),
                bin_hz=self.config.bin_hz,
                grace_ms=self.config.delivery_grace_ms,
                emit=self.journal.bin,
            )
            self.receipts = RoundReceipts(
                tuple(self.readers), self.grid, self.journal.event
            )
            self.reference.command(config)
            self._accepting = True
            self.reference.command(struct.pack("!4sQ", b"CGGO", self.run_id))
            sync_id, last_sync = 8, time.monotonic()
            while not self._stop.wait(0.01) and not self.failure:
                if time.monotonic() - last_sync >= 1:
                    self.reference.sync(sync_id)
                    sync_id += 1
                    last_sync = time.monotonic()
                    self.journal.event(
                        "gateway_host_buffer", **self._usb_buffer.stats()
                    )
                now = time.monotonic_ns()
                self.grid.advance(now)
                self.receipts.advance(now)
                for key, heartbeat in self._receiver_heartbeats.items():
                    self.readers[key].connected = time.monotonic() - heartbeat < 2.5
        except Exception as exc:
            self._fail(str(exc))
        finally:
            if self.reference:
                try:
                    self.reference.command(
                        struct.pack("!4sQ", b"CGSP", self.run_id), timeout=0.5
                    )
                except Exception:
                    pass  # The independent host-control lease also stops sensing.
            # A host stop ends grants; records already forwarded may finish ingestion.
            until = time.monotonic() + self.config.drain_ms / 1000
            while time.monotonic() < until and not self.failure:
                if self.grid:
                    self.grid.advance(time.monotonic_ns())
                    self.receipts.advance(time.monotonic_ns())
                time.sleep(0.01)
            if self.connection:
                try:
                    self._write(CONTROL, struct.pack("!4sQ", b"CGSP", self.run_id))
                except Exception:
                    pass
            self._stop_gateway_usb()
            if self.journal:
                self.journal.event(
                    "gateway_host_buffer", final=True, **self._usb_buffer.stats()
                )
            if self.reference:
                self.reference.stop()
            for recorder in self._recorders.values():
                if recorder:
                    recorder.close()
            for state in self.readers.values():
                state._close_packet_stream()
            if self.journal:
                self.journal.close()
            if owned_io:
                try:
                    self.recording_io.close()
                except Exception as exc:
                    self._recording_shutdown_error = exc
                    self._fail(f"recording shutdown failed: {exc}")

    def _open_gateway(self) -> None:
        factory = self.serial_factory
        if factory is None:
            from serial import Serial

            factory = Serial
        self.connection = factory(
            self.gateway_port, 921600, timeout=0.005, write_timeout=0.5, exclusive=True
        )
        if os.name == "posix" and self.serial_factory is None:
            from .native import require_native, PipelineStats
            self._native_pipeline = require_native().Pipeline(
                self.connection.fileno(), maximum_age_ns=self._usb_buffer.maximum_age_ns
            )
            self._usb_buffer = PipelineStats(self._native_pipeline)
        self._usb_thread = Thread(
            target=self._read_usb, name="csi-gateway-usb", daemon=True
        )
        if self._native_pipeline is None:
            self._usb_drain_thread = Thread(
                target=self._drain_gateway_usb, name="csi-gateway-usb-drain", daemon=True
            )
            self._usb_drain_thread.start()
        self._usb_thread.start()
        self._write(5, b"")
        if not self._status_ready.wait(2):
            raise TimeoutError("gateway discovery timed out")
        if self.failure:
            raise RuntimeError(self.failure)

    def _stop_gateway_usb(self) -> None:
        """Stop reads, process owned bytes, then release the USB descriptor."""
        self._usb_stop.set()
        if self._native_pipeline is not None:
            self._native_pipeline.request_stop()
        if self._usb_drain_thread:
            self._usb_drain_thread.join(2)
        self._usb_buffer.close()
        if self._usb_thread:
            self._usb_thread.join(2)
        if self._native_pipeline is not None:
            self._native_pipeline.close()
        if any(
            worker and worker.is_alive()
            for worker in (self._usb_drain_thread, self._usb_thread)
        ):
            self._shutdown_error = "gateway USB shutdown did not drain"
            self._fail(self._shutdown_error)
            raise TimeoutError(self._shutdown_error)
        if self.connection:
            self.connection.close()

    def start(self) -> None:
        """Start acquisition without blocking the GUI event loop."""
        self._thread.start()

    def stop(self) -> None:
        """Stop sensing and drain bounded in-progress host acceptance."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=6)
            if self._thread.is_alive():
                raise TimeoutError("gateway shutdown did not complete")
        if self._shutdown_error:
            raise TimeoutError(self._shutdown_error)
        if self._recording_shutdown_error:
            raise self._recording_shutdown_error

    @property
    def buffer(self) -> RollingCsiBuffer:
        return (
            next(iter(self.readers.values())).buffer
            if self.readers
            else self._fallback_buffer
        )

    @property
    def clock_sync_ready(self) -> bool:
        return bool(self.reference and self.reference.ready and not self.failure)

    @property
    def preview_ready(self) -> bool:
        """Allow expensive plot work only after reference processing catches up.

        This affects display frames only. Sensing, recording, clock validation
        and acquisition failure thresholds are independent of the preview.
        """
        queued = self._usb_buffer.stats()
        return bool(
            self.reference
            and not self.failure
            and getattr(self.reference, "usb_backlog_chunks", 0) <= 16
            and queued["queued_chunks"] <= PREVIEW_MAX_QUEUED_CHUNKS
            and queued["oldest_age_ns"] <= PREVIEW_MAX_QUEUE_AGE_NS
            and queued.get("application_oldest_age_ns", 0) <= PREVIEW_MAX_QUEUE_AGE_NS
            and queued.get("completed_frames", 0) <= 64
        )

    @property
    def clock_sync(self) -> ClockSyncEstimator | None:
        return self.reference.estimator if self.reference else None

    @property
    def all_live(self) -> bool:
        return (
            bool(self.readers)
            and all(s.connected for s in self.readers.values())
            and not self.failure
        )

    @property
    def any_recent_record(self) -> bool:
        return bool(self.readers) and all(
            s.last_valid_time is not None and time.monotonic() - s.last_valid_time < 2.5
            for s in self.readers.values()
        )

    @property
    def preflight_ready(self) -> bool:
        return self.all_live and self.any_recent_record and self.clock_sync_ready

    @property
    def last_valid_time(self) -> float | None:
        values = [s.last_valid_time for s in self.readers.values()]
        return min(values) if values and all(v is not None for v in values) else None

    def telemetry_snapshot(self) -> BackhaulTelemetrySnapshot:
        """Aggregate decoder counters; retain gateway/receiver diagnostics in journals."""
        snapshots = [s.telemetry_snapshot() for s in self.readers.values()]
        names = (
            "records",
            "batches",
            "host_missing_sequences",
            "transport_missing",
            "transport_reordered",
            "batch_missing",
            "batch_reordered",
            "malformed",
            "foreign",
            "receiver_restarts",
        )
        return BackhaulTelemetrySnapshot(
            captured_monotonic_ns=time.monotonic_ns(),
            **{k: sum(getattr(s, k) for s in snapshots) for k in names},
            serial_frames=None,
            receiver_boot_id=None,
            receiver_stats=None,
            transmitter_stats=None,
            gateway_stats=None,
        )

    def diagnostics(self, *, now_ns: int | None = None) -> GatewayDiagnostics:
        """Snapshot actual gateway counters; unavailable values stay unreported.

        Receiver states are last reports on the 5 GHz control link. They do not
        establish a receiver's current channel or explain sequence gaps.
        """
        now_ns = time.monotonic_ns() if now_ns is None else now_ns
        now = now_ns / 1e9
        rates = self._delivery_rates.snapshot(now_ns)
        receivers = []
        for key, state in self.readers.items():
            status = dict(state.status)
            heartbeat = self._receiver_heartbeats.get(key)
            age = None if heartbeat is None else max(0.0, now - heartbeat)
            receivers.append(
                ReceiverDiagnostics(
                    receiver_id=key,
                    status_age_s=age,
                    delivery_age_s=None
                    if state.last_valid_time is None
                    else max(0.0, now - state.last_valid_time),
                    online=bool(
                        age is not None
                        and age < 2.5
                        and state.connected
                        and not state.profile_mismatch
                        and not self.failure
                    ),
                    reported_state=status.get("state"),
                    records=state.buffer.received_records,
                    records_s=rates.get(key, 0.0),
                    last_sequence=state.buffer.last_sequence,
                    captured=status.get("captured"),
                    queued=status.get("queued"),
                    queue_peak=status.get("peak"),
                    expired=status.get("expired"),
                    dropped=status.get("dropped"),
                    send_errors=status.get("send_errors"),
                    diagnostic_loss=status.get("queue_event_loss"),
                    sequence_gaps=state.buffer.missing_sequences,
                    transport_gaps=state.transport_missing,
                    batch_gaps=state.batch_missing,
                    malformed_packets=state.malformed_lines,
                )
            )
        estimate = self.reference.estimator.estimate if self.reference else None
        gateway = dict(self.gateway_status)
        return GatewayDiagnostics(
            nominal_rate_hz=self.profile.nominal_rate_hz,
            sensing_channel=self.profile.channel,
            backhaul_channel=self.config.channel,
            backhaul_phy=self.config.phy,
            slot_ms=self.config.slot_ms,
            queue_capacity=self.config.queue_capacity,
            application_acknowledgements=self.config.application_acknowledgements,
            transmitter_link=self.transmitter_link,
            reference_present=self.reference is not None,
            reference_ready=self.clock_sync_ready,
            clock_uncertainty_us=estimate.uncertainty_us if estimate else None,
            gateway_age_s=None
            if self._gateway_status_ns is None
            else max(0.0, (now_ns - self._gateway_status_ns) / 1e9),
            gateway_configured=gateway.get("configured"),
            received_envelopes=gateway.get("received"),
            forwarded_envelopes=gateway.get("forwarded"),
            rejected_or_dropped=gateway.get("rejected"),
            usb_errors=gateway.get("usb_errors"),
            gateway_queued=gateway.get("queued"),
            failure=self.failure,
            receivers=tuple(receivers),
        )

    def diagnostic_text(self) -> str:
        return "\n".join(
            f"{key}: {'ready' if s.connected else 'offline'}; "
            f"queue {s.status.get('queued', '—')}; expired {s.status.get('expired', '—')}; "
            f"captured {s.status.get('captured', '—')}"
            for key, s in self.readers.items()
        )
