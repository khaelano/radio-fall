"""Direct USB receiver acquisition with hub-safe identity binding."""

from __future__ import annotations

from dataclasses import dataclass
import struct
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .buffer import RollingCsiBuffer
from .clock_sync import ClockSyncEstimator, decode_clock_sync_sample
from .packet_reader import BinaryCsiPacketReader
from .serial_framing import (
    TYPE_DEVICE_STATUS,
    TYPE_CLOCK_SYNC,
    TYPE_CLOCK_SYNC_REQUEST,
    TYPE_DISCOVER_REQUEST,
    SerialFrameStreamDecoder,
    encode_serial_frame,
)
from ..profile import RadioInventory, RadioProfile, profile_fingerprint
from ..provisioning import DeviceStatus
from .telemetry import BackhaulTelemetrySnapshot


@dataclass(frozen=True)
class UsbReceiverBinding:
    """A discovered receiver identity and its current tty path."""

    receiver_id: str
    mac: str
    target: str
    port: str
    profile_fingerprint: str | None
    ready: bool = False


class UsbReceiverCsiReader(BinaryCsiPacketReader):
    """Reconnectable binary reader for one receiver's native USB stream."""

    def __init__(
        self,
        binding: UsbReceiverBinding,
        buffer: RollingCsiBuffer,
        output_dir: Path,
        *,
        on_status: Optional[Callable[[str, bool], None]] = None,
        record_sink: Optional[Callable[[object, int], None]] = None,
        clock_sync_sink: Optional[Callable[[object, object, int], None]] = None,
        rebind_port: Optional[Callable[[str], str | None]] = None,
        expected_profile_fingerprint: str | None = None,
    ) -> None:
        super().__init__(
            buffer,
            output_dir,
            receiver_mac=binding.mac,
            on_status=on_status,
            live_status=f"USB receiver {binding.receiver_id} stream live",
            record_sink=record_sink,
            profile_fingerprint=expected_profile_fingerprint,
            require_profile_fingerprint=True,
        )
        self.binding = binding
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._run,
            name=f"csi-usb-{binding.receiver_id}",
            daemon=True,
        )
        self.port = binding.port
        self.last_status: DeviceStatus | None = None
        self.clock_sync = ClockSyncEstimator()
        self.clock_sync_sink = clock_sync_sink
        self._sync_id = 0
        self.rebind_port = rebind_port
        self.profile_mismatch = False
        self.connected = False

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)

    def _run(self) -> None:
        try:
            import serial
            from serial import SerialException
        except ImportError:
            self._status("pyserial is not installed", False)
            return

        backoff = 0.5
        while not self.stop_event.is_set():
            try:
                self._status(f"opening receiver {self.binding.receiver_id}: {self.port}", False)
                # Do not touch DTR/RTS: pyserial already leaves both asserted,
                # and driving them low is what resets the native USB-Serial/JTAG
                # MCU on open.
                with serial.Serial(self.port, 921600, timeout=0.25) as connection:
                    connection.write(encode_serial_frame(TYPE_DISCOVER_REQUEST, b""))
                    decoder = SerialFrameStreamDecoder()
                    self.connected = False
                    self._status(f"USB receiver {self.binding.receiver_id} connected", True)
                    backoff = 0.5
                    while not self.stop_event.is_set():
                        if (
                            self.last_status is not None
                            and time.monotonic() - getattr(self, "_last_sync_request", 0.0) >= 1.0
                        ):
                            self._request_clock_sync(connection)
                        chunk = connection.read(max(1, getattr(connection, "in_waiting", 0)))
                        if not chunk:
                            continue
                        for frame in decoder.feed(chunk):
                            if frame.type == TYPE_DEVICE_STATUS:
                                try:
                                    self.last_status = DeviceStatus.from_payload(frame.payload)
                                    self.profile_mismatch = (
                                        self.last_status.profile_fingerprint
                                        != self.profile_fingerprint
                                        or not self.last_status.ready
                                    )
                                    self.connected = not self.profile_mismatch
                                    if self.profile_mismatch:
                                        self._status(
                                            f"receiver {self.binding.receiver_id} profile mismatch",
                                            False,
                                        )
                                except Exception:
                                    self.malformed_lines += 1
                                continue
                            if frame.type == TYPE_CLOCK_SYNC:
                                try:
                                    sample = decode_clock_sync_sample(frame.payload)
                                    estimate = self.clock_sync.add(sample)
                                    if self.clock_sync_sink is not None:
                                        self.clock_sync_sink(
                                            sample, estimate, time.monotonic_ns()
                                        )
                                except Exception:
                                    self.malformed_lines += 1
                                continue
                            self._ingest_packet(frame.payload)
            except (SerialException, OSError) as exc:
                if self.stop_event.is_set():
                    break
                self._status(f"receiver {self.binding.receiver_id} USB error: {exc}", False)
            finally:
                self.connected = False
                self._stream_live = False
                self._close_packet_stream()
            if self.stop_event.is_set():
                break
            if self.rebind_port is not None:
                rebound = self.rebind_port(self.binding.mac)
                if rebound is not None:
                    self.port = rebound
            self._status(f"receiver {self.binding.receiver_id} disconnected; retrying", False)
            self.stop_event.wait(backoff)
            backoff = min(backoff * 2.0, 5.0)

    def _request_clock_sync(self, connection: object) -> None:
        """Request a host↔receiver exchange over the same framed USB link."""

        t1_us = time.monotonic_ns() // 1000
        payload = struct.pack("!IQ", self._sync_id, t1_us)
        self._sync_id = (self._sync_id + 1) & 0xFFFFFFFF
        connection.write(encode_serial_frame(TYPE_CLOCK_SYNC_REQUEST, payload))
        self._last_sync_request = time.monotonic()


def discover_usb_receivers() -> tuple[UsbReceiverBinding, ...]:
    """Probe all serial ports and return only framed receiver identities."""

    try:
        import serial
        from serial.tools import list_ports
    except ImportError as exc:
        raise RuntimeError("pyserial is required for USB acquisition") from exc

    bindings: list[UsbReceiverBinding] = []
    for port in sorted(list_ports.comports(), key=lambda item: item.device):
        connection = None
        try:
            connection = serial.Serial(port.device, 921600, timeout=0.1)
            connection.write(encode_serial_frame(TYPE_DISCOVER_REQUEST, b""))
            decoder = SerialFrameStreamDecoder()
            status: DeviceStatus | None = None
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline and status is None:
                chunk = connection.read(max(1, getattr(connection, "in_waiting", 0)))
                if not chunk:
                    continue
                for frame in decoder.feed(chunk):
                    if frame.type == TYPE_DEVICE_STATUS:
                        status = DeviceStatus.from_payload(frame.payload)
                        break
            if status is not None and status.role == "receiver":
                bindings.append(
                    UsbReceiverBinding(
                        receiver_id=status.mac,
                        mac=status.mac,
                        target=status.target,
                        port=port.device,
                        profile_fingerprint=status.profile_fingerprint,
                        ready=status.ready,
                    )
                )
        except Exception:
            pass
        finally:
            if connection is not None:
                connection.close()
    return tuple(bindings)


class UsbReceiverManager:
    """Bind configured receiver IDs to changing USB port names."""

    def __init__(
        self,
        inventory: RadioInventory,
        profile: RadioProfile,
        output_dir: Path,
        *,
        on_status: Optional[Callable[[str, bool], None]] = None,
        record_sink: Optional[Callable[[object, int], None]] = None,
        clock_sync_sink: Optional[Callable[[object, object, int], None]] = None,
    ) -> None:
        self.inventory = inventory
        self.profile = profile
        self.output_dir = output_dir
        self.on_status = on_status
        self.record_sink = record_sink
        self.clock_sync_sink = clock_sync_sink
        self.expected_fingerprint = profile_fingerprint(profile, inventory)
        self.readers: dict[str, UsbReceiverCsiReader] = {}
        self.bindings: dict[str, UsbReceiverBinding] = {}

    def bind(self) -> tuple[UsbReceiverBinding, ...]:
        discovered = discover_usb_receivers()
        by_mac = {device.mac: device for device in self.inventory.receivers}
        bindings: list[UsbReceiverBinding] = []
        seen_macs: set[str] = set()
        for binding in discovered:
            expected = by_mac.get(binding.mac)
            if expected is None:
                raise RuntimeError(f"unknown receiver MAC discovered: {binding.mac}")
            if binding.mac in seen_macs:
                raise RuntimeError(f"receiver {expected.id} discovered on multiple USB ports")
            seen_macs.add(binding.mac)
            if expected.target != binding.target:
                raise RuntimeError(f"receiver {expected.id} target mismatch")
            if not binding.ready or binding.profile_fingerprint != self.expected_fingerprint:
                raise RuntimeError(
                    f"receiver {expected.id} has no matching provisioned profile"
                )
            bindings.append(
                UsbReceiverBinding(
                    receiver_id=expected.id,
                    mac=binding.mac,
                    target=binding.target,
                    port=binding.port,
                    profile_fingerprint=binding.profile_fingerprint,
                    ready=binding.ready,
                )
            )
        if len(bindings) != len(self.inventory.receivers):
            raise RuntimeError(
                f"expected {len(self.inventory.receivers)} receivers, found {len(bindings)}"
            )
        for binding in bindings:
            self.readers[binding.receiver_id] = UsbReceiverCsiReader(
                binding,
                RollingCsiBuffer(nominal_rate=self.profile.nominal_rate_hz, seconds=3),
                self.output_dir / "receivers" / binding.receiver_id,
                on_status=self.on_status,
                record_sink=self.record_sink,
                clock_sync_sink=self.clock_sync_sink,
                rebind_port=self._rebind_port,
                expected_profile_fingerprint=self.expected_fingerprint,
            )
        self.bindings = {binding.receiver_id: binding for binding in bindings}
        return tuple(bindings)

    def _rebind_port(self, mac: str) -> str | None:
        """Find a receiver's new tty after a powered-hub reconnect."""

        return next(
            (binding.port for binding in discover_usb_receivers() if binding.mac == mac),
            None,
        )

    def start(self) -> None:
        if not self.readers:
            self.bind()
        for reader in self.readers.values():
            reader.start()

    def stop(self) -> None:
        for reader in self.readers.values():
            reader.stop()

    @property
    def buffer(self) -> RollingCsiBuffer:
        """Expose one receiver buffer for the shared CSI preview widget."""

        if not self.readers:
            # ``bind`` is normally called before the GUI is built.  This
            # fallback keeps diagnostics importable when no USB boards exist.
            return RollingCsiBuffer(nominal_rate=self.profile.nominal_rate_hz, seconds=3)
        return next(iter(self.readers.values())).buffer

    @property
    def last_valid_time(self) -> float | None:
        values = [reader.last_valid_time for reader in self.readers.values()]
        return min(values) if values and all(value is not None for value in values) else None

    @property
    def clock_sync(self) -> object:
        """Compatibility view: USB framing is host-clocked once all boards are live."""

        return self

    @property
    def estimate(self) -> object | None:
        return object() if self.clock_sync_ready else None

    def telemetry_snapshot(self) -> BackhaulTelemetrySnapshot:
        snapshots = [reader.telemetry_snapshot() for reader in self.readers.values()]
        if not snapshots:
            return BackhaulTelemetrySnapshot(
                captured_monotonic_ns=time.monotonic_ns(),
                records=0,
                batches=0,
                host_missing_sequences=0,
                transport_missing=0,
                transport_reordered=0,
                batch_missing=0,
                batch_reordered=0,
                malformed=0,
                foreign=0,
                receiver_restarts=0,
                serial_frames=0,
                receiver_boot_id=None,
                receiver_stats=None,
                transmitter_stats=None,
                gateway_stats=None,
            )
        return BackhaulTelemetrySnapshot(
            captured_monotonic_ns=time.monotonic_ns(),
            records=sum(item.records for item in snapshots),
            batches=sum(item.batches for item in snapshots),
            host_missing_sequences=sum(item.host_missing_sequences for item in snapshots),
            transport_missing=sum(item.transport_missing for item in snapshots),
            transport_reordered=sum(item.transport_reordered for item in snapshots),
            batch_missing=sum(item.batch_missing for item in snapshots),
            batch_reordered=sum(item.batch_reordered for item in snapshots),
            malformed=sum(item.malformed for item in snapshots),
            foreign=sum(item.foreign for item in snapshots),
            receiver_restarts=sum(item.receiver_restarts for item in snapshots),
            serial_frames=sum(item.serial_frames or 0 for item in snapshots),
            receiver_boot_id=None,
            receiver_stats=None,
            transmitter_stats=None,
            gateway_stats=None,
        )

    @property
    def all_live(self) -> bool:
        """Whether every configured receiver is connected and profile-valid."""

        return bool(self.readers) and all(
            reader.connected and not reader.profile_mismatch
            for reader in self.readers.values()
        )

    @property
    def any_recent_record(self) -> bool:
        """Whether every receiver has produced a recent packet."""

        now = time.monotonic()
        return bool(self.readers) and all(
            reader.last_valid_time is not None and now - reader.last_valid_time < 2.5
            for reader in self.readers.values()
        )

    @property
    def clock_sync_ready(self) -> bool:
        return self.all_live and all(
            reader.clock_sync.estimate is not None for reader in self.readers.values()
        )
