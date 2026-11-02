"""Scheduled dual-band acquisition through a dedicated C6 USB gateway."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
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
from .packet_reader import BinaryCsiPacketReader
from .recorder import CsiRecorder
from .protocol import CsiRecord
from .clock_sync import ClockSyncEstimator
from .serial_framing import SerialFrameStreamDecoder, encode_serial_frame
from .telemetry import BackhaulTelemetrySnapshot
from .transmitter_reference import TransmitterReference


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
    """Coordinate two USB links, recorder acceptance and causal availability.

    Factories are injectable for deterministic offline tests. Hardware startup
    requires explicitly named USB ports; receiver slot order is never discovered.
    """

    def __init__(
        self,
        inventory: RadioInventory,
        profile: RadioProfile,
        output_dir: Path,
        *,
        transmitter_port: str,
        gateway_port: str,
        config: EspnowTransportConfig | None = None,
        require_four: bool = False,
        on_status: Callable[[str, bool], None] | None = None,
        record_sink: Callable[[CsiRecord, int], None] | None = None,
        journal_root: Path | Callable[[], Path | None] | None = None,
        reference_failure_sink: Callable[[str], None] | None = None,
        serial_factory: Callable[..., Any] | None = None,
        reference_factory: Callable[..., Any] | None = None,
        run_id: int | None = None,
    ) -> None:
        self.inventory, self.profile, self.output_dir = inventory, profile, output_dir
        self.transmitter_port, self.gateway_port = transmitter_port, gateway_port
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
        self.expected_fingerprint = profile_fingerprint(profile, inventory)
        self.bindings, self.readers = {}, {}
        self.reference = self.journal = self.grid = self.receipts = self.connection = (
            None
        )
        self.gateway_status = {}
        self.failure = None
        self._stop, self._status_ready, self._response_ready = Event(), Event(), Event()
        self._usb_stop = Event()
        self._write_lock, self._command_lock = Lock(), Lock()
        self._responses = deque(maxlen=16)
        self._thread = Thread(target=self._run, name="csi-gateway", daemon=True)
        self._usb_thread = None
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
            not self.transmitter_port
            or not self.gateway_port
            or self.transmitter_port == self.gateway_port
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
        if self.failure is None:
            self.failure = message
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
                    self.output_dir / receiver_id
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
        )

    def accept(self, data: bytes, arrival_ns: int) -> bool:
        """Validate and record atomically at the application level before ACK."""
        batch = GatewayBatch.decode(data)
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
        from .wire import decode_csi_packet

        packet = decode_csi_packet(batch.payload)
        if any(
            r.record.profile_fingerprint != self.expected_fingerprint
            for r in packet.records
        ):
            raise ValueError("gateway sensing profile mismatch")
        self.journal.accept(batch, arrival_ns)
        if batch.identity not in self._accepted:
            if not state.ingest_packet(
                batch.payload,
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
            self._accepted.add(batch.identity)
            self._accepted_order.append(batch.identity)
            if len(self._accepted_order) > 4096:
                self._accepted.discard(self._accepted_order.popleft())
        if self.config.application_acknowledgements:
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

    def _read_usb(self) -> None:
        import json

        decoder = SerialFrameStreamDecoder()
        last_errors = (0, 0)
        try:
            while not self._usb_stop.is_set():
                data = self.connection.read(
                    max(1, min(4096, getattr(self.connection, "in_waiting", 1)))
                )
                for frame in decoder.feed(data):
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
                        self._status_ready.set()
                        if self.journal:
                            self.journal.event("gateway_status", **status)
                    elif frame.type == RESPONSE:
                        self._responses.append(frame.payload)
                        self._response_ready.set()
                    elif frame.type == ENVELOPE:
                        self.accept(frame.payload, time.monotonic_ns())
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
        except Exception as exc:
            if not self._stop.is_set():
                self._fail(f"gateway ingestion failed: {exc}")

    def _run(self) -> None:
        try:
            if not self.readers:
                self.bind()
            root = (
                self.journal_root()
                if callable(self.journal_root)
                else self.journal_root
            )
            root = root or self.output_dir / f"gateway-{self.run_id:016x}"
            self.journal = GatewayJournal(
                root,
                self.run_id,
                dict(
                    transport="espnow_gateway",
                    transport_config=asdict(self.config),
                    transport_fingerprint=self.config.fingerprint(
                        self.inventory, self.profile
                    ),
                    inventory=self.inventory.as_dict(),
                    profile=self.profile.as_dict(),
                ),
            )
            self.reference = self.reference_factory(
                self.transmitter_port,
                self.inventory.transmitter.mac,
                self._event,
                failure_sink=self._fail,
                expected_profile_fingerprint=self.expected_fingerprint,
                expected_sensing_phy="he20",
                expected_sensing_version=4,
                expected_sensing_rate_hz=self.profile.nominal_rate_hz,
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
            factory = self.serial_factory
            if factory is None:
                from serial import Serial

                factory = Serial
            self.connection = factory(
                self.gateway_port,
                921600,
                timeout=0.1,
                write_timeout=0.5,
                exclusive=True,
            )
            self._usb_thread = Thread(
                target=self._read_usb, name="csi-gateway-usb", daemon=True
            )
            self._usb_thread.start()
            self._write(5, b"")
            if not self._status_ready.wait(2):
                raise TimeoutError("gateway discovery timed out")
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
            self._usb_stop.set()
            if self.connection:
                self.connection.close()
            if self._usb_thread:
                self._usb_thread.join(2)
            if self.reference:
                self.reference.stop()
            for recorder in self._recorders.values():
                if recorder:
                    recorder.close()
            for state in self.readers.values():
                state._close_packet_stream()
            if self.journal:
                self.journal.close()

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

    def diagnostic_text(self) -> str:
        return "\n".join(
            f"{key}: {'ready' if s.connected else 'offline'}; "
            f"queue {s.status.get('queued', '—')}; expired {s.status.get('expired', '—')}; "
            f"captured {s.status.get('captured', '—')}"
            for key, s in self.readers.items()
        )
