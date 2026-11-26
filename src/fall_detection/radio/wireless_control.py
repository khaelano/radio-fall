"""One-time USB pairing and connectionless transmitter status/provisioning."""

from __future__ import annotations

import json
import secrets
import struct
import time
from collections.abc import Callable
from threading import Condition, Event, Lock, Thread
from typing import Any

from .profile import RadioInventory
from .provisioning import (
    TYPE_WIRELESS_REQUEST,
    DeviceStatus,
    ProvisioningError,
    SerialFrameStreamDecoder,
    SerialProvisioningDevice,
    encode_serial_frame,
)


class WirelessReferenceSerial:
    """Reuse strict reference validation over a reliable gateway bridge.

    Gateway acceptance of a request is not transmitter execution. Responses and
    authoritative round logs must traverse the bridge before readers see them.
    """

    def __init__(self, write: Callable[[int, bytes], None], capacity: int = 262144):
        self._write = write
        self._capacity = capacity
        self._buffer = bytearray()
        self._condition = Condition()
        self._closed = False
        self._decoder = SerialFrameStreamDecoder()

    @property
    def in_waiting(self) -> int:
        """Return buffered reference bytes without reading the gateway directly."""
        with self._condition:
            return len(self._buffer)

    def feed(self, payload: bytes) -> None:
        """Accept one demultiplexed response, preserving original serial framing."""
        if not payload:
            raise ValueError("empty wireless reference response")
        if payload[0]:
            framed = encode_serial_frame(payload[0], payload[1:])
        else:
            pieces = []
            offset = 1
            while offset < len(payload):
                if len(payload) - offset < 3:
                    raise ValueError("truncated wireless reference batch")
                kind, size = struct.unpack_from("!BH", payload, offset)
                offset += 3
                if not kind or size > len(payload) - offset:
                    raise ValueError("invalid wireless reference batch")
                pieces.append(
                    encode_serial_frame(kind, payload[offset : offset + size])
                )
                offset += size
            if not pieces:
                raise ValueError("empty wireless reference batch")
            framed = b"".join(pieces)
        with self._condition:
            if self._closed:
                return
            if len(self._buffer) + len(framed) > self._capacity:
                raise BufferError("wireless reference queue overflow")
            self._buffer.extend(framed)
            self._condition.notify_all()

    def write(self, data: bytes) -> int:
        """Submit complete requests; the firmware owns reliable radio delivery."""
        if self._closed:
            raise OSError("wireless reference closed")
        for frame in self._decoder.feed(data):
            if len(frame.payload) + 3 >= 1280:
                raise ValueError("wireless command exceeds bridge limit")
            self._write(TYPE_WIRELESS_REQUEST, bytes([frame.type]) + frame.payload)
        return len(data)

    def read(self, size: int) -> bytes:
        """Return available data, waiting at most the serial-compatible 100 ms."""
        deadline = time.monotonic() + 0.1
        with self._condition:
            while not self._buffer and not self._closed:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return b""
                self._condition.wait(remaining)
            count = min(max(size, 0), len(self._buffer))
            data = bytes(self._buffer[:count])
            del self._buffer[:count]
            return data

    def close(self) -> None:
        """Wake readers without closing the shared gateway USB connection."""
        with self._condition:
            self._closed = True
            self._condition.notify_all()


class WirelessProvisioningDevice(SerialProvisioningDevice):
    """Wait for the advertised commit ACK and intentional reboot to settle."""

    def refresh_status(self) -> DeviceStatus:
        time.sleep(1)
        # An idle peer reboot discards old transport requests. Retry only this
        # read; staging and commit are never blindly repeated.
        for attempt in range(3):
            try:
                return super().refresh_status()
            except ProvisioningError:
                if attempt == 2:
                    raise


class GatewayWirelessPort:
    """Own one gateway port for standalone setup, separate from acquisition."""

    def __init__(
        self,
        port: str,
        serial_factory: Callable[..., Any] | None = None,
        transmitter_link: str = "espnow_uart",
    ) -> None:
        if transmitter_link != "espnow_uart":
            raise ValueError("unsupported wireless transmitter link")
        self._prefix = "relay"
        self._version = 1
        if serial_factory is None:
            from serial import Serial

            serial_factory = Serial
        self.connection = serial_factory(
            port, 921600, timeout=0.1, write_timeout=0.5, exclusive=True
        )
        self._lock = Lock()
        self._stop = Event()
        self.failure = None
        self.gateway_status = {}
        self._status_ready = Event()
        self.serial = WirelessReferenceSerial(self._write)
        self._thread = Thread(target=self._read, daemon=True)
        self._thread.start()
        try:
            self._write(5, b"")
            if not self._status_ready.wait(2):
                raise TimeoutError("gateway setup discovery timed out")
            if self.gateway_status.get(
                f"{self._prefix}_version"
            ) != self._version or not self.gateway_status.get(f"{self._prefix}_paired"):
                raise RuntimeError(
                    "gateway lacks the paired wireless reference firmware"
                )
            if self.gateway_status.get("relay_transport") != "espnow_uart":
                raise RuntimeError("gateway relay transport mismatch")
            deadline = time.monotonic() + 8
            while (
                not self.failure
                and not self.gateway_status.get(f"{self._prefix}_ready")
                and time.monotonic() < deadline
            ):
                time.sleep(0.05)
            if self.failure or not self.gateway_status.get(f"{self._prefix}_ready"):
                raise RuntimeError(
                    self.failure or "wireless reference handshake timed out"
                )
        except Exception:
            self.close()
            raise

    def _write(self, kind: int, payload: bytes) -> None:
        if self.failure:
            raise RuntimeError(self.failure)
        with self._lock:
            self.connection.write(encode_serial_frame(kind, payload))

    def _read(self) -> None:
        decoder = SerialFrameStreamDecoder()
        try:
            while not self._stop.is_set():
                chunk = self.connection.read(
                    max(1, min(4096, self.connection.in_waiting))
                )
                for frame in decoder.feed(chunk):
                    if frame.type == 27:
                        self.serial.feed(frame.payload)
                    elif frame.type == 6:
                        status = json.loads(frame.payload)
                        self.gateway_status = status
                        self._status_ready.set()
                        if status.get(f"{self._prefix}_fault"):
                            raise RuntimeError(
                                "wireless reference failed: "
                                + status.get(
                                    f"{self._prefix}_failure_reason", "unknown"
                                )
                                + "; reset both endpoints"
                            )
        except Exception as exc:  # noqa: BLE001 — thread error boundary
            if not self._stop.is_set():
                self.failure = str(exc)
                self.serial.close()

    def close(self) -> None:
        """Close the setup session without changing hardware reset lines."""
        self._stop.set()
        self._thread.join(2)
        self.connection.close()
        self.serial.close()


def discover_port(connection, timeout: float = 3) -> dict:
    """Read framed discovery without resetting the identified board."""
    decoder = SerialFrameStreamDecoder()
    connection.write(encode_serial_frame(5, b""))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for frame in decoder.feed(
            connection.read(max(1, min(4096, connection.in_waiting)))
        ):
            if frame.type == 6:
                return json.loads(frame.payload)
    raise TimeoutError("wireless setup discovery timed out")


def pair_devices(
    tx_port: str,
    gateway_port: str,
    inventory: RadioInventory,
    *,
    transmitter_link: str = "espnow_uart",
    channel: int = 6,
) -> None:
    """Verify both identities before storing a fresh shared key over USB.

    Keys are never printed or included in experiment journals. Pairing reboots
    both boards and must be performed with sensing stopped.
    """
    from serial import Serial

    if transmitter_link != "espnow_uart" or not 1 <= channel <= 13:
        raise ValueError("invalid pairing transport/channel")
    if tx_port == gateway_port:
        raise ValueError("distinct identified transmitter/gateway ports required")
    devices = []
    identities = []
    try:
        for port, expected in (
            (tx_port, inventory.transmitter),
            (gateway_port, inventory.gateway),
        ):
            connection = Serial(
                port, 921600, timeout=0.1, write_timeout=0.5, exclusive=True
            )
            devices.append(connection)
            raw = discover_port(connection)
            identities.append(raw)
            if expected is inventory.transmitter:
                if (raw.get("role"), raw.get("target"), raw.get("relay_version")) != (
                    "relay",
                    "esp32c6",
                    1,
                ):
                    raise ValueError("pairing requires the UART companion C6 USB port")
            else:
                if (
                    raw.get("role"),
                    raw.get("target"),
                    raw.get("mac"),
                    raw.get("relay_version"),
                ) != ("gateway", "esp32c6", expected.mac, 1):
                    raise ValueError("pairing relay gateway identity mismatch")
            if raw.get("radio_active") or raw.get("configured"):
                raise ValueError("stop sensing before pairing")
        source_mac = identities[0]["mac"]
        payload = (
            b"CRPS"
            + bytes.fromhex(source_mac.replace(":", ""))
            + bytes.fromhex(inventory.gateway.mac.replace(":", ""))
            + secrets.token_bytes(32)
        )
        payload += bytes([channel])
        for connection in devices:
            # A separate response adapter avoids printing the pairing payload.
            adapter = SerialProvisioningDevice(
                connection, DeviceStatus("", "", "", "", 3)
            )
            if adapter._request(28, 29, payload) != b"ok":
                raise RuntimeError("pairing rejected; rerun on both boards")
    finally:
        for connection in devices:
            connection.close()
