"""Four-receiver BLE acquisition with a USB transmitter reference."""

from __future__ import annotations

import asyncio
import math
import secrets
import struct
import time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event, Thread
from typing import Any, Callable

from ..ble_config import (
    CONTROL_UUID,
    DATA_UUID,
    SERVICE_UUID,
    STATS_UUID,
    STATUS_UUID,
    TIMING_UUID,
    FLOW_UUID,
    BleTransportConfig,
    inventory_crc,
    flow_token,
)
from ..profile import RadioInventory, RadioProfile, profile_fingerprint
from .availability import AvailabilityGrid, RoundReceipts
from .ble_journal import BleJournal
from .ble_protocol import (
    BleBatch,
    BleReassembler,
    decode_status,
    FlowFragment,
    progress_receipt,
    decode_flow_status,
)
from .ble_reference import BleTransmitterReference
from .buffer import RollingCsiBuffer
from .packet_reader import BinaryCsiPacketReader
from .protocol import CsiRecord
from .telemetry import BackhaulTelemetrySnapshot


@dataclass(frozen=True)
class BleReceiverBinding:
    """Stable receiver identity, independent of its current BLE address."""

    receiver_id: str
    mac: str
    target: str
    port: str = "ble"
    profile_fingerprint: str | None = None
    ready: bool = False


class BleIngestionError(RuntimeError):
    """Storage/consumer failure requiring the run to stop without an ACK."""


class BleReceiverState(BinaryCsiPacketReader):
    """Shared ingestion state plus bounded BLE connection/reassembly state."""

    def __init__(
        self,
        binding: BleReceiverBinding,
        profile: RadioProfile,
        output_dir: Path,
        record_sink: Callable[[CsiRecord, int], None],
        status_sink: Callable[[str, bool], None] | None,
    ) -> None:
        super().__init__(
            RollingCsiBuffer(nominal_rate=profile.nominal_rate_hz, seconds=3),
            output_dir,
            receiver_mac=binding.mac,
            record_sink=record_sink,
            on_status=status_sink,
            profile_fingerprint=binding.profile_fingerprint,
            require_profile_fingerprint=True,
            live_status=f"BLE {binding.receiver_id} live",
        )
        self.binding = binding
        self.connected = False
        self.profile_mismatch = False
        self.status: dict = {}
        self.reassembler = BleReassembler()
        self.notifications: asyncio.Queue | None = None
        self.client = None
        self.notification_drops = 0
        self.notification_generation = None
        self.flow_serial: int | None = None
        self.flow_since_progress = 0
        self.flow_event: asyncio.Event | None = None
        self.flow_progress_writes = 0
        self.reconnects = 0
        self._accepted = set()
        self._accepted_order = deque()


class BleReceiverManager:
    """Keep receivers independent while enforcing one shared run/reference.

    Scanner, client and reference factories are injectable for offline tests.
    No receiver USB connections are opened by this adapter.
    """

    def __init__(
        self,
        inventory: RadioInventory,
        profile: RadioProfile,
        output_dir: Path,
        *,
        transmitter_port: str,
        config: BleTransportConfig | None = None,
        require_four: bool = False,
        allow_missing_receivers: bool = False,
        on_status: Callable[[str, bool], None] | None = None,
        record_sink: Callable[[CsiRecord, int], None] | None = None,
        journal_root: Path | Callable[[], Path] | None = None,
        reference_failure_sink: Callable[[str], None] | None = None,
        scanner: Any = None,
        client_factory: Callable[..., Any] | None = None,
        reference_factory: Callable[..., Any] | None = None,
        run_id: int | None = None,
    ) -> None:
        self.inventory = inventory
        self.profile = profile
        self.output_dir = output_dir
        self.transmitter_port = transmitter_port
        self.config = config or BleTransportConfig()
        self.require_four = require_four
        if self.config.experiment is not None and (
            require_four or not allow_missing_receivers
        ):
            raise ValueError("timing experiments require explicit development mode")
        if require_four and allow_missing_receivers:
            raise ValueError("collection cannot allow missing receivers at startup")
        self.allow_missing_receivers = allow_missing_receivers
        self._startup_receiver_ids: tuple[str, ...] = ()
        self.on_status = on_status
        self.record_sink = record_sink
        self.journal_root = journal_root
        self.reference_failure_sink = reference_failure_sink
        self.scanner = scanner
        self.client_factory = client_factory
        self.hardware_backend = (
            scanner is None and client_factory is None and reference_factory is None
        )
        self.reference_factory = reference_factory or BleTransmitterReference
        self.run_id = run_id or secrets.randbits(64) or 1
        self.receiver_macs = tuple(d.mac for d in inventory.receivers)
        self.expected_fingerprint = profile_fingerprint(profile, inventory)
        self.readers: dict[str, BleReceiverState] = {}
        self.bindings: dict[str, BleReceiverBinding] = {}
        self.journal: BleJournal | None = None
        self.reference = None
        self.grid = None
        self.receipts = None
        self.failure: str | None = None
        self._stop = Event()
        self._disconnecting = False
        self._accept_tasks: set[asyncio.Task] = set()
        self._thread = Thread(target=self._thread_main, name="csi-ble", daemon=True)
        self._fallback_buffer = RollingCsiBuffer(
            nominal_rate=profile.nominal_rate_hz, seconds=3
        )

    def bind(self) -> tuple[BleReceiverBinding, ...]:
        """Prepare configured slots without scanning or changing their order."""
        count = len(self.inventory.receivers)
        if not 1 <= count <= 4 or (self.require_four and count != 4):
            raise RuntimeError(
                "BLE collection requires four registered receivers; development supports one to four"
            )
        if not self.transmitter_port:
            raise RuntimeError("BLE requires --port for the USB transmitter reference")
        self.config.encode(
            self.run_id,
            count,
            self.profile.nominal_rate_hz,
            receiver_macs=self.receiver_macs,
        )
        for device in self.inventory.receivers:
            binding = BleReceiverBinding(
                device.id,
                device.mac,
                device.target,
                profile_fingerprint=self.expected_fingerprint,
            )
            self.bindings[device.id] = binding
            self.readers[device.id] = BleReceiverState(
                binding,
                self.profile,
                self.output_dir / device.id,
                self._record,
                self.on_status,
            )
        for state in self.readers.values():
            state.reassembler = BleReassembler(
                capacity=self.config.outstanding_batches,
                timeout=self.config.drain_ms / 1000,
                replace_oldest=True,
            )
        return tuple(self.bindings.values())

    def _status(self, message: str, connected: bool = False) -> None:
        if self.on_status:
            self.on_status(message, connected)

    def _reference_failed(self, message: str) -> None:
        self.failure = message
        self._status(message, False)
        if self.reference_failure_sink:
            self.reference_failure_sink(message)

    def _event(self, kind: str, **values) -> None:
        if self.journal:
            self.journal.event(kind, **values)
        if kind == "round" and self.receipts:
            self.receipts.round(values)

    def _record(self, record, arrival_ns: int) -> None:
        if self.record_sink:
            self.record_sink(record, arrival_ns)
        available_ns = time.monotonic_ns()
        receiver_id = next(
            d.id for d in self.inventory.receivers if d.mac == record.receiver_mac
        )
        timely = None
        if self.grid and record.capture_host_monotonic_ns is not None:
            timely = self.grid.observe(
                receiver_id, record.capture_host_monotonic_ns, available_ns
            )
        if self.receipts:
            self.receipts.receive(
                record.transmitter_boot_id, record.sequence, receiver_id, available_ns
            )
        if self.journal:
            self.journal.event(
                "record",
                receiver_mac=record.receiver_mac,
                run_id=str(record.run_id),
                transmitter_boot_id=record.transmitter_boot_id,
                receiver_boot_id=record.receiver_boot_id,
                sequence=record.sequence,
                capture_host_ns=record.capture_host_monotonic_ns,
                arrival_ns=arrival_ns,
                available_ns=available_ns,
                timely=timely,
                tx_enqueue_us=record.tx_timestamp_us,
                rx_callback_us=record.rx_callback_timestamp_us,
                rx_radio_us=record.timestamp_us,
                clock_uncertainty_us=record.capture_clock_uncertainty_us,
                finite_slots=[
                    bool(math.isfinite(v.real) and math.isfinite(v.imag))
                    for v in record.csi
                ],
            )

    def _accept(
        self, state: BleReceiverState, batch: BleBatch, arrival_ns: int
    ) -> None:
        if batch.run_id != self.run_id:
            raise ValueError("stale BLE run")
        if batch.transmitter_boot_id != self.reference.transmitter_boot_id:
            raise ValueError("BLE transmitter epoch does not match USB reference")
        if batch.receiver_boot_id != state.status.get("boot_id"):
            raise ValueError("BLE receiver boot changed before identity verification")
        # Verify receiver and profile before persisting or acknowledging a packet.
        from .wire import decode_csi_packet

        packet = decode_csi_packet(batch.payload)
        if any(
            item.receiver_mac != state.receiver_mac
            or item.record.profile_fingerprint != self.expected_fingerprint
            for item in packet.records
        ):
            raise ValueError("BLE receiver or profile mismatch")
        self.journal.accept(batch, arrival_ns)
        key = (
            batch.run_id,
            batch.transmitter_boot_id,
            batch.receiver_boot_id,
            batch.batch_id,
        )
        if key not in state._accepted:
            ok = state.ingest_packet(
                batch.payload,
                host_receive_monotonic_ns=arrival_ns,
                context=dict(
                    run_id=batch.run_id,
                    transmitter_boot_id=batch.transmitter_boot_id,
                    receiver_boot_id=batch.receiver_boot_id,
                    capture_clock_uncertainty_us=getattr(
                        self.reference.estimator.estimate, "uncertainty_us", None
                    ),
                ),
                capture_clock=self.reference.capture_time,
            )
            if not ok:
                raise ValueError("shared CSI ingestion rejected BLE batch")
            state._accepted.add(key)
            state._accepted_order.append(key)
            if len(state._accepted_order) > 4096:
                state._accepted.discard(state._accepted_order.popleft())

    def _notification(self, state, data: bytes, generation=None) -> None:
        if generation is not None and generation is not state.notification_generation:
            return
        try:
            state.notifications.put_nowait((time.monotonic_ns(), bytes(data)))
        except asyncio.QueueFull:
            state.notification_drops += 1

    async def _consume(self, state: BleReceiverState, client) -> None:
        while True:
            arrival, fragment = await state.notifications.get()
            try:
                if self.config.experiment and self.config.experiment.delivery:
                    item = FlowFragment.decode(fragment, flow_token(self.run_id))
                    previous = state.flow_serial
                    if (
                        previous is None
                        or 0 < ((item.serial - previous) & 0xFFFFFFFF) < 0x80000000
                    ):
                        state.flow_serial = item.serial
                        state.flow_since_progress += 1
                        state.flow_event.set()
                    fragment = item.classic
                batch = state.reassembler.feed(fragment, arrival / 1e9)
                if batch is None:
                    continue
                first_arrival = state.reassembler.last_completed_started
                processing_started = time.monotonic_ns()
                try:
                    processing = asyncio.create_task(
                        asyncio.to_thread(self._accept, state, batch, arrival)
                    )
                    self._accept_tasks.add(processing)
                    processing.add_done_callback(self._accept_tasks.discard)
                    await asyncio.shield(processing)
                except (OSError, RuntimeError, BufferError) as exc:
                    raise BleIngestionError(str(exc)) from exc
                accepted = time.monotonic_ns()
                await asyncio.wait_for(
                    client.write_gatt_char(
                        CONTROL_UUID, batch.acknowledgement(), response=False
                    ),
                    timeout=2,
                )
                if self.config.experiment is not None:
                    self._event(
                        "batch_host_timing",
                        receiver=state.binding.receiver_id,
                        receiver_boot_id=batch.receiver_boot_id,
                        batch_id=batch.batch_id,
                        first_fragment_ns=int(first_arrival * 1e9),
                        last_fragment_ns=arrival,
                        processing_started_ns=processing_started,
                        accepted_ns=accepted,
                        ack_submitted_ns=time.monotonic_ns(),
                    )
            except ValueError as exc:
                state.malformed_lines += 1
                self._event(
                    "batch_rejected",
                    receiver=state.binding.receiver_id,
                    detail=str(exc),
                )
            finally:
                state.notifications.task_done()

    async def _progress(self, state: BleReceiverState, client) -> None:
        """Return bounded transport credits independently of recorder acceptance.

        Receipts are coalesced and repeated after 50 ms to recover a lost write.
        They never free original records; the existing validated batch ACK does.
        """
        policy = self.config.experiment.delivery
        last_sent = None
        last_time = 0.0
        while True:
            try:
                await asyncio.wait_for(
                    state.flow_event.wait(), policy.progress_interval_ms / 1000
                )
            except asyncio.TimeoutError:
                pass
            state.flow_event.clear()
            serial = state.flow_serial
            now = time.monotonic()
            if serial is None:
                continue
            changed = last_sent is None or serial != last_sent
            if not (
                (
                    changed
                    and (
                        state.flow_since_progress >= policy.progress_every
                        or now - last_time >= policy.progress_interval_ms / 1000
                    )
                )
                or now - last_time >= 0.05
            ):
                continue
            receipt = progress_receipt(
                self.run_id,
                self.reference.transmitter_boot_id,
                state.status["boot_id"],
                flow_token(self.run_id),
                serial,
            )
            state.flow_since_progress = 0
            await asyncio.wait_for(
                client.write_gatt_char(CONTROL_UUID, receipt, response=False), 1
            )
            state.flow_progress_writes += 1
            last_sent = serial
            last_time = time.monotonic()

    def _verify_identity(self, state, status, configured: bool = False) -> None:
        expected = (
            status.get("protocol_version") == 1
            and status.get("sensing_version") == 3
            and status.get("role") == "receiver"
            and status.get("target") == state.binding.target
            and status.get("mac", "").lower() == state.binding.mac
            and status.get("profile_fingerprint") == self.expected_fingerprint
            and status.get("inventory_crc") == inventory_crc(self.receiver_macs)
        )
        if configured:
            expected = expected and (
                str(status.get("run_id")) == str(self.run_id)
                and status.get("transport_fingerprint") == self.config.fingerprint
                and status.get("ready") is True
            )
        state.profile_mismatch = not expected
        if not expected:
            raise ValueError(
                f"identity/configuration mismatch for {state.binding.receiver_id}"
            )

    async def _read_status(self, client) -> dict:
        identity = bytes(await asyncio.wait_for(client.read_gatt_char(STATUS_UUID), 2))
        diagnostics = bytes(
            await asyncio.wait_for(client.read_gatt_char(STATS_UUID), 2)
        )
        return decode_status(identity, diagnostics)

    async def _receiver(self, state, device) -> None:
        while not self._disconnecting:
            consumer = None
            progress_worker = None
            try:
                client = self.client_factory(device)
                async with client:
                    status = await self._read_status(client)
                    self._verify_identity(state, status)
                    state.status = status
                    state.client = client
                    state.reassembler.clear()
                    state.notifications = asyncio.Queue(maxsize=128)
                    generation = object()
                    state.notification_generation = generation
                    state.flow_serial = None
                    state.flow_since_progress = 0
                    state.flow_event = asyncio.Event()
                    await client.start_notify(
                        DATA_UUID,
                        lambda _, data, g=generation: self._notification(
                            state, data, g
                        ),
                    )
                    await client.write_gatt_char(
                        CONTROL_UUID,
                        self.config.encode(
                            self.run_id,
                            len(self.readers),
                            self.profile.nominal_rate_hz,
                            receiver_macs=self.receiver_macs,
                        ),
                        response=True,
                    )
                    status = await self._read_status(client)
                    self._verify_identity(state, status, configured=True)
                    if self.config.experiment is not None:
                        wanted = self.config.experiment.connection_interval_units
                        # The connect-time request can still be in progress when
                        # CBLC arrives. Retry before sensing, never during a trial.
                        for _ in range(2):
                            if status.get("interval_units") == wanted:
                                break
                            await asyncio.sleep(0.5)
                            await client.write_gatt_char(
                                CONTROL_UUID,
                                self.config.encode(
                                    self.run_id,
                                    len(self.readers),
                                    self.profile.nominal_rate_hz,
                                    receiver_macs=self.receiver_macs,
                                ),
                                response=True,
                            )
                            await asyncio.sleep(0.5)
                            status = await self._read_status(client)
                            self._verify_identity(state, status, configured=True)
                        if status.get("interval_units") != wanted:
                            self._reference_failed(
                                f"experimental interval not negotiated: requested {wanted}, "
                                f"actual {status.get('interval_units')}"
                            )
                            raise ValueError("experimental interval not negotiated")
                    state.status = status
                    state.last_valid_time = None
                    state.connected = True
                    consumer = asyncio.create_task(self._consume(state, client))
                    if self.config.experiment and self.config.experiment.delivery:
                        progress_worker = asyncio.create_task(
                            self._progress(state, client)
                        )
                    self._event(
                        "receiver_connected",
                        receiver=state.binding.receiver_id,
                        status=status,
                    )
                    self._status(f"BLE {state.binding.receiver_id} connected", True)
                    while not self._disconnecting and client.is_connected:
                        await asyncio.sleep(1.0)
                        if consumer.done():
                            consumer.result()
                        if progress_worker and progress_worker.done():
                            progress_worker.result()
                        status = await self._read_status(client)
                        self._verify_identity(state, status, configured=True)
                        if status.get("boot_id") != state.status.get("boot_id"):
                            raise ValueError(
                                "receiver restarted; reconnect for a fresh identity"
                            )
                        state.status = status
                        services = getattr(client, "services", None)
                        if (
                            self.config.experiment
                            and services is not None
                            and services.get_characteristic(FLOW_UUID)
                        ):
                            status.update(
                                decode_flow_status(
                                    bytes(
                                        await asyncio.wait_for(
                                            client.read_gatt_char(FLOW_UUID), 2
                                        )
                                    )
                                )
                            )
                        self._event(
                            "receiver_status",
                            receiver=state.binding.receiver_id,
                            status=status,
                            notification_drops=state.notification_drops,
                            reassembly_evictions=state.reassembler.evicted,
                            reassembly_expired=state.reassembler.expired,
                            reassembly_stale_fragments=state.reassembler.stale_fragments,
                            flow_progress_writes=state.flow_progress_writes,
                        )
                        if self.config.experiment is not None:
                            raw = bytes(
                                await asyncio.wait_for(
                                    client.read_gatt_char(TIMING_UUID), 2
                                )
                            )
                            from .ble_protocol import decode_timing

                            self._event(
                                "receiver_timing",
                                receiver=state.binding.receiver_id,
                                receiver_boot_id=status["boot_id"],
                                batches=decode_timing(raw),
                            )
            except asyncio.CancelledError:
                raise
            except BleIngestionError as exc:
                self._reference_failed(f"BLE ingestion failed: {exc}")
            except Exception as exc:
                self._status(f"BLE {state.binding.receiver_id}: {exc}")
            finally:
                state.connected = False
                state.notification_generation = None
                state.client = None
                if consumer:
                    consumer.cancel()
                    await asyncio.gather(consumer, return_exceptions=True)
                if progress_worker:
                    progress_worker.cancel()
                    await asyncio.gather(progress_worker, return_exceptions=True)
                self._event("receiver_disconnected", receiver=state.binding.receiver_id)
            if not self._disconnecting:
                state.reconnects += 1
                await asyncio.sleep(0.5)

    async def _clock_loop(self) -> None:
        identity = 100
        while not self._disconnecting:
            await asyncio.sleep(1)
            try:
                await asyncio.to_thread(self.reference.sync, identity)
                identity = (identity + 1) & 0xFFFFFFFF
            except Exception as exc:
                self._reference_failed(f"USB clock reference failed: {exc}")
                return

    async def _run(self) -> None:
        workers = []
        clock_task = None
        try:
            if self.hardware_backend:
                raise RuntimeError(
                    "Live BLE acquisition is retired; use the ESP-NOW gateway transport"
                )
            if self.scanner is None or self.client_factory is None:
                from bleak import BleakClient, BleakScanner

                self.scanner = self.scanner or BleakScanner
                self.client_factory = self.client_factory or (
                    lambda device: BleakClient(device, timeout=5)
                )
            root = (
                self.journal_root()
                if callable(self.journal_root)
                else self.journal_root
            )
            root = (
                Path(root)
                if root is not None
                else self.output_dir / f"ble-{self.run_id:016x}"
            )
            self.journal = BleJournal(
                root,
                self.run_id,
                dict(
                    transport_config=asdict(self.config),
                    hardware_backend=self.hardware_backend,
                    development_allow_missing_receivers=self.allow_missing_receivers,
                    transport_fingerprint=self.config.fingerprint,
                    radio_profile=self.profile.as_dict(),
                    profile_fingerprint=self.expected_fingerprint,
                    inventory=self.inventory.as_dict(),
                    transmitter_port=self.transmitter_port,
                ),
            )
            self.reference = self.reference_factory(
                self.transmitter_port,
                self.inventory.transmitter.mac,
                self._event,
                failure_sink=self._reference_failed,
                expected_profile_fingerprint=self.expected_fingerprint,
                expected_sensing_phy="he20",
                expected_sensing_version=3,
            )
            self.reference.run_id = self.run_id
            self.reference.start()
            self._event(
                "transmitter_status",
                status=getattr(self.reference, "device_status", None),
            )
            await asyncio.to_thread(
                self.reference.command,
                self.config.encode(
                    self.run_id,
                    len(self.readers),
                    self.profile.nominal_rate_hz,
                    receiver_macs=self.receiver_macs,
                ),
            )
            for identity in range(8):
                await asyncio.to_thread(self.reference.sync, identity)
                await asyncio.sleep(0.05)
            clock_task = asyncio.create_task(self._clock_loop())
            devices = await self.scanner.discover(
                timeout=5, service_uuids=[SERVICE_UUID]
            )
            # Bind by GATT identity, never advertisement name or enumeration order.
            matches = {}
            for device in devices:
                if self._stop.is_set():
                    raise RuntimeError("BLE startup stopped")
                async with self.client_factory(device) as client:
                    status = await self._read_status(client)
                mac = str(status.get("mac", "")).lower()
                if mac in matches:
                    raise RuntimeError(f"duplicate advertised receiver identity: {mac}")
                if mac in {d.mac for d in self.inventory.receivers}:
                    matches[mac] = device
            for state in self.readers.values():
                if state.binding.mac not in matches:
                    if self.allow_missing_receivers:
                        self._event(
                            "receiver_not_discovered",
                            receiver=state.binding.receiver_id,
                        )
                        continue
                    raise RuntimeError(
                        f"BLE receiver not discovered: {state.binding.receiver_id}"
                    )
                workers.append(
                    asyncio.create_task(
                        self._receiver(state, matches[state.binding.mac])
                    )
                )
            self._startup_receiver_ids = tuple(
                key
                for key, state in self.readers.items()
                if state.binding.mac in matches
            )
            if not self._startup_receiver_ids:
                raise RuntimeError("no registered BLE receivers discovered")
            self._event("startup_receivers", receivers=self._startup_receiver_ids)
            deadline = time.monotonic() + 30
            while not all(
                self.readers[key].connected and not self.readers[key].profile_mismatch
                for key in self._startup_receiver_ids
            ):
                if self.failure or time.monotonic() >= deadline or self._stop.is_set():
                    raise RuntimeError(
                        self.failure or "BLE receiver preflight timed out"
                    )
                await asyncio.sleep(0.05)
            if not self.reference.ready:
                raise RuntimeError("transmitter clock fit is unavailable")
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
            self._event("sensing_started", start_ns=self.grid.start_ns)
            await asyncio.to_thread(
                self.reference.command, struct.pack("!4sQ", b"CBGO", self.run_id)
            )
            while not self._stop.is_set() and not self.failure:
                now = time.monotonic_ns()
                self.grid.advance(now)
                self.receipts.advance(now)
                if not self.reference.ready:
                    self._reference_failed("transmitter clock reference became stale")
                elif (
                    self.reference.last_round_time is None
                    or time.monotonic() - self.reference.last_round_time > 2
                ):
                    # Allow startup latency, but do not keep an unobserved transmitter live.
                    if now - self.grid.start_ns > 2_000_000_000:
                        self._reference_failed("transmitter round reference stopped")
                await asyncio.sleep(0.02)
        except Exception as exc:
            self._reference_failed(str(exc))
        finally:
            if self.reference:
                try:
                    await asyncio.to_thread(
                        self.reference.command,
                        struct.pack("!4sQ", b"CBST", self.run_id),
                    )
                except Exception:
                    pass
            drains = [
                asyncio.wait_for(
                    state.client.write_gatt_char(
                        CONTROL_UUID,
                        struct.pack(
                            "!4sQH", b"CBDS", self.run_id, self.config.drain_ms
                        ),
                        response=True,
                    ),
                    1,
                )
                for state in self.readers.values()
                if state.connected and state.client
            ]
            await asyncio.gather(*drains, return_exceptions=True)
            await asyncio.sleep(self.config.drain_ms / 1000)
            self._disconnecting = True
            for task in workers + ([clock_task] if clock_task else []):
                task.cancel()
            await asyncio.gather(
                *workers, *([clock_task] if clock_task else []), return_exceptions=True
            )
            if self._accept_tasks:
                await asyncio.gather(*self._accept_tasks, return_exceptions=True)
            if self.grid:
                now = time.monotonic_ns()
                self.grid.advance(now)
                self.receipts.advance(now)
            if self.reference:
                self.reference.stop()
            if self.journal:
                self.journal.event(
                    "run_finished",
                    failure=self.failure,
                    statuses={r: state.status for r, state in self.readers.items()},
                )
                self.journal.close()

    def _thread_main(self) -> None:
        asyncio.run(self._run())

    def start(self) -> None:
        """Start a single owned event loop without blocking the GUI."""
        if not self.readers:
            self.bind()
        self._thread.start()

    def stop(self) -> None:
        """Stop sensing, drain bounded pending delivery, and close connections."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=12)
        if self._thread.is_alive():
            raise TimeoutError("BLE shutdown did not finish")

    @property
    def buffer(self) -> RollingCsiBuffer:
        """Expose a receiver buffer for the existing dashboard contract."""
        return (
            next(iter(self.readers.values())).buffer
            if self.readers
            else self._fallback_buffer
        )

    @property
    def preflight_ready(self) -> bool:
        """Require fresh decoding from startup devices; collection still needs all."""
        now = time.monotonic()
        return (
            bool(self._startup_receiver_ids)
            and self.clock_sync_ready
            and all(
                self.readers[key].connected
                and not self.readers[key].profile_mismatch
                and self.readers[key].last_valid_time is not None
                and now - self.readers[key].last_valid_time < 2.5
                for key in self._startup_receiver_ids
            )
        )

    @property
    def all_live(self) -> bool:
        """Require every configured identity for starting a new attempt."""
        return bool(self.readers) and all(
            s.connected and not s.profile_mismatch for s in self.readers.values()
        )

    @property
    def any_recent_record(self) -> bool:
        """Require every receiver to demonstrate real decoding during preflight."""
        now = time.monotonic()
        return bool(self.readers) and all(
            s.last_valid_time is not None and now - s.last_valid_time < 2.5
            for s in self.readers.values()
        )

    @property
    def last_valid_time(self) -> float | None:
        """Return the oldest latest observation across all receiver slots."""
        values = [s.last_valid_time for s in self.readers.values()]
        return min(values) if values and all(v is not None for v in values) else None

    @property
    def clock_sync_ready(self) -> bool:
        """Receiver loss does not invalidate an intact transmitter reference."""
        return bool(self.reference and self.reference.ready and not self.failure)

    @property
    def clock_sync(self) -> Any:
        """Expose the reference through the existing GUI health interface."""
        return self.reference.estimator if self.reference else None

    def telemetry_snapshot(self) -> BackhaulTelemetrySnapshot:
        """Aggregate existing counters; detailed BLE status remains in the journal."""
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
            **{name: sum(getattr(s, name) for s in snapshots) for name in names},
            serial_frames=None,
            receiver_boot_id=None,
            receiver_stats=None,
            transmitter_stats=None,
            gateway_stats=None,
        )

    def diagnostic_text(self) -> str:
        """Summarize per-receiver queue state and cumulative timely availability."""
        lines = []
        elapsed = (
            max(0.001, (time.monotonic_ns() - self.grid.start_ns) / 1e9)
            if self.grid
            else 0
        )
        for receiver, state in self.readers.items():
            s = state.status
            rate = self.grid.timely[receiver] / elapsed if elapsed else 0
            lines.append(
                f"{receiver}: {'connected' if state.connected else 'offline'}; "
                f"timely {rate:.1f}/s; queue {s.get('queued', '—')}; "
                f"oldest {s.get('oldest_age_us', 0) / 1000:.0f} ms; expired {s.get('expired', '—')}; "
                f"gaps {state.buffer.missing_sequences}; PHY {s.get('tx_phy', '—')}; MTU {s.get('mtu', '—')}"
            )
        if self.reference and self.reference.estimator.estimate:
            lines.append(
                f"USB clock uncertainty {self.reference.estimator.estimate.uncertainty_us:.0f} us"
            )
        return "\n".join(lines)
