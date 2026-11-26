"""USB discovery and radio-profile provisioning for groups or individual boards.

The host speaks one small framed JSON control protocol to both transmitter
and receiver firmware.  The transport adapter is deliberately separate from
profile validation so validation and commit semantics can be tested without
physical USB boards.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from .native import require_native
from .profile import (
    RadioInventory,
    RadioProfile,
    RadioProfileError,
    profile_fingerprint,
)

# --- CRC-protected COBS serial framing (native implementation) ---

TYPE_CSI_PACKET = 1
TYPE_TRANSMITTER_STATS = 2
TYPE_GATEWAY_STATS = 3
TYPE_CLOCK_SYNC = 4
TYPE_DISCOVER_REQUEST = 5
TYPE_DEVICE_STATUS = 6
TYPE_PROFILE_STAGE = 7
TYPE_PROFILE_STAGE_ACK = 8
TYPE_PROFILE_COMMIT = 9
TYPE_PROFILE_COMMIT_ACK = 10
TYPE_CLOCK_SYNC_REQUEST = 11
TYPE_GATEWAY_CONTROL = 20
TYPE_GATEWAY_RESPONSE = 21
TYPE_GATEWAY_ROUND = 22
TYPE_GATEWAY_EVENT = 23
TYPE_GATEWAY_ENVELOPE = 24
TYPE_GATEWAY_ACK = 25
TYPE_WIRELESS_REQUEST = 26
TYPE_WIRELESS_RESPONSE = 27
TYPE_WIRELESS_PAIR = 28
TYPE_WIRELESS_PAIR_ACK = 29
TYPE_RELAY_RECOVER = 31
KNOWN_TYPES = {
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    TYPE_CSI_PACKET,
    TYPE_TRANSMITTER_STATS,
    TYPE_GATEWAY_STATS,
    TYPE_CLOCK_SYNC,
    TYPE_DISCOVER_REQUEST,
    TYPE_DEVICE_STATUS,
    TYPE_PROFILE_STAGE,
    TYPE_PROFILE_STAGE_ACK,
    TYPE_PROFILE_COMMIT,
    TYPE_PROFILE_COMMIT_ACK,
    TYPE_CLOCK_SYNC_REQUEST,
    TYPE_RELAY_RECOVER,
}
MAX_PAYLOAD = 1400


class SerialFrameError(ValueError):
    """Raised when one serial gateway frame is malformed."""


@dataclass(frozen=True)
class SerialFrame:
    """One decoded gateway frame."""

    type: int
    payload: bytes


def encode_serial_frame(frame_type: int, payload: bytes) -> bytes:
    """Encode a gateway frame using the native transport implementation."""
    if frame_type not in KNOWN_TYPES:
        raise SerialFrameError("unknown serial frame type")
    if len(payload) > MAX_PAYLOAD:
        raise SerialFrameError("serial frame payload exceeds 1400 bytes")
    return require_native().encode_frame(frame_type, payload)


def decode_serial_frame(encoded: bytes) -> SerialFrame:
    """Decode a single delimiter-free frame using the native implementation."""
    decoder = require_native().FrameDecoder()
    frames = decoder.feed(b"\x00" + encoded + b"\x00")
    if decoder.malformed_frames or decoder.oversized_frames or len(frames) != 1:
        raise SerialFrameError("invalid serial frame")
    return SerialFrame(*frames[0])


class SerialFrameStreamDecoder:
    """Decode incoming serial frames using the native transport layer."""

    def __init__(self) -> None:
        self._native = require_native().FrameDecoder()
        self.malformed_frames = 0
        self.oversized_frames = 0

    def feed(self, data: bytes) -> list[SerialFrame]:
        """Consume bytes and return every complete valid frame."""
        values = self._native.feed(data)
        self.malformed_frames = self._native.malformed_frames
        self.oversized_frames = self._native.oversized_frames
        return [SerialFrame(kind, payload) for kind, payload in values]


class ProvisioningError(RuntimeError):
    """Raised when discovery or a provisioning phase fails."""


@dataclass(frozen=True)
class DeviceStatus:
    """Status reported by one connected firmware image."""

    role: str
    target: str
    mac: str
    firmware_version: str
    protocol_version: int
    profile_fingerprint: str | None = None
    profile_id: str | None = None
    ready: bool = False
    csi_transport: str | None = None
    reset_reason: str | None = None
    uptime_ms: int | None = None
    radio_active: bool | None = None
    tx_power_quarter_dbm: int | None = None
    board: str | None = None
    antenna: str | None = None
    sensing_phy: str | None = None
    sensing_version: int | None = None

    @classmethod
    def from_payload(cls, payload: bytes) -> DeviceStatus:
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProvisioningError("device status is not valid JSON") from exc
        if not isinstance(value, dict):
            raise ProvisioningError("device status must be an object")
        try:
            return cls(
                role=str(value["role"]),
                target=str(value["target"]).lower(),
                mac=str(value["mac"]).lower(),
                firmware_version=str(value.get("firmware_version", "unknown")),
                protocol_version=int(value["protocol_version"]),
                profile_fingerprint=(
                    str(value["profile_fingerprint"])
                    if value.get("profile_fingerprint")
                    else None
                ),
                profile_id=(
                    str(value["profile_id"]) if value.get("profile_id") else None
                ),
                ready=bool(value.get("ready", False)),
                csi_transport=value.get("csi_transport"),
                reset_reason=value.get("reset_reason"),
                uptime_ms=value.get("uptime_ms"),
                radio_active=value.get("radio_active"),
                tx_power_quarter_dbm=value.get("tx_power_quarter_dbm"),
                board=value.get("board"),
                antenna=value.get("antenna"),
                sensing_phy=value.get("sensing_phy"),
                sensing_version=value.get("sensing_version"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProvisioningError("device status is missing required fields") from exc


class ProvisioningDevice(Protocol):
    """Small adapter interface required by :class:`RadioProvisioner`."""

    @property
    def status(self) -> DeviceStatus: ...

    def stage_profile(self, payload: bytes) -> None: ...

    def commit_profile(self) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class ProvisioningReport:
    """Successful provisioning result, suitable for session metadata."""

    profile_id: str
    fingerprint: str
    devices: tuple[DeviceStatus, ...]


def _profile_payload(
    inventory: RadioInventory, profile: RadioProfile, fingerprint: str
) -> bytes:
    value = {
        "schema_version": 1,
        "profile": profile.as_dict(),
        "fingerprint": fingerprint,
        "transmitter_mac": inventory.transmitter.mac,
        # The untethered transmitter sends unicast sensing frames at a fixed HE
        # rate, so it needs the receiver addresses stored in its profile.
        "receivers": [device.mac for device in inventory.receivers],
        "wire_version": 2,
    }
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(payload) > 1200:
        raise ProvisioningError("radio profile control payload is too large")
    return payload


class RadioProvisioner:
    """Validate connected identities before staging one shared profile.

    Sequential mode requires exactly one connected board while retaining the
    complete inventory in its payload. Other boards are not checked in that mode.
    """

    def __init__(self, devices: Iterable[ProvisioningDevice]) -> None:
        self.devices = tuple(devices)

    def preflight(
        self,
        inventory: RadioInventory,
        profile: RadioProfile,
        *,
        sequential: bool = False,
    ) -> tuple[tuple[ProvisioningDevice, DeviceStatus], ...]:
        """Validate all configured boards, or one registered board sequentially."""
        expected = {inventory.transmitter.mac: inventory.transmitter}
        expected.update({device.mac: device for device in inventory.receivers})
        expected[inventory.gateway.mac] = inventory.gateway
        required_count = 1 if sequential else len(expected)
        if len(self.devices) != required_count:
            raise ProvisioningError(
                f"expected {required_count} devices, discovered {len(self.devices)}"
                + (
                    "; --sequential requires exactly one connected board"
                    if sequential
                    else ""
                )
            )
        bound: list[tuple[ProvisioningDevice, DeviceStatus]] = []
        seen: set[str] = set()
        for device in self.devices:
            status = device.status
            if status.mac in seen:
                raise ProvisioningError(
                    f"duplicate device MAC discovered: {status.mac}"
                )
            seen.add(status.mac)
            expected_device = expected.get(status.mac)
            if expected_device is None:
                raise ProvisioningError(f"unknown device MAC discovered: {status.mac}")
            if (
                status.role != expected_device.role
                or status.target != expected_device.target
            ):
                raise ProvisioningError(
                    f"device {status.mac} role/target does not match inventory"
                )
            if status.protocol_version != 3:
                raise ProvisioningError(
                    f"device {status.mac} uses unsupported protocol"
                )
            bound.append((device, status))
        try:
            profile_fingerprint(profile, inventory)
        except RadioProfileError as exc:
            raise ProvisioningError(str(exc)) from exc
        # Re-provisioning an already-provisioned device is how band or channel
        # gets changed, so a differing active profile must not block preflight.
        # Even sequential mode validates capabilities against the full inventory.
        return tuple(bound)

    def provision(
        self,
        inventory: RadioInventory,
        profile: RadioProfile,
        *,
        sequential: bool = False,
    ) -> ProvisioningReport:
        """Stage, commit and verify the selected boards using the full inventory."""
        bound = self.preflight(inventory, profile, sequential=sequential)
        fingerprint = profile_fingerprint(profile, inventory)
        payload = _profile_payload(inventory, profile, fingerprint)
        staged: list[ProvisioningDevice] = []
        verified: list[DeviceStatus] = []
        try:
            for device, _status in bound:
                if _status.role == "gateway":
                    verified.append(_status)
                    continue
                device.stage_profile(payload)
                staged.append(device)
            for device in staged:
                device.commit_profile()
            for device, _status in bound:
                if _status.role == "gateway":
                    continue
                refresh = getattr(device, "refresh_status", None)
                if refresh is None:
                    verified.append(device.status)
                    continue
                status = refresh()
                if status.profile_fingerprint != fingerprint or not status.ready:
                    raise ProvisioningError(
                        f"device {status.mac} did not report the committed profile"
                    )
                verified.append(status)
        except Exception as exc:
            raise ProvisioningError(
                "profile provisioning did not complete; rerun provisioning to recover"
            ) from exc
        return ProvisioningReport(
            profile_id=profile.profile_id,
            fingerprint=fingerprint,
            devices=tuple(verified),
        )


class SerialProvisioningDevice:
    """PySerial adapter for the framed JSON provisioning protocol."""

    def __init__(
        self, connection: Any, status: DeviceStatus, timeout: float = 2.0
    ) -> None:
        self.connection = connection
        self._status = status
        self.timeout = timeout
        self.decoder = SerialFrameStreamDecoder()

    @property
    def status(self) -> DeviceStatus:
        return self._status

    def _request(
        self, request_type: int, response_type: int, payload: bytes = b""
    ) -> bytes:
        self.connection.write(encode_serial_frame(request_type, payload))
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            chunk = self.connection.read(
                max(1, getattr(self.connection, "in_waiting", 0))
            )
            if not chunk:
                continue
            for frame in self.decoder.feed(chunk):
                if frame.type == response_type:
                    return frame.payload
        raise ProvisioningError(
            f"timed out waiting for response {response_type} from {self.status.mac}"
        )

    def stage_profile(self, payload: bytes) -> None:
        response = self._request(TYPE_PROFILE_STAGE, TYPE_PROFILE_STAGE_ACK, payload)
        if response not in (b"ok", b"OK"):
            raise ProvisioningError(f"device {self.status.mac} rejected staged profile")

    def commit_profile(self) -> None:
        response = self._request(TYPE_PROFILE_COMMIT, TYPE_PROFILE_COMMIT_ACK)
        if response not in (b"ok", b"OK"):
            raise ProvisioningError(f"device {self.status.mac} rejected profile commit")

    def refresh_status(self) -> DeviceStatus:
        """Read the post-reboot status used to verify an atomic commit."""

        time.sleep(0.6)
        payload = self._request(TYPE_DISCOVER_REQUEST, TYPE_DEVICE_STATUS)
        self._status = DeviceStatus.from_payload(payload)
        return self._status

    def close(self) -> None:
        self.connection.close()


ESPRESSIF_USB_VID = 0x303A
DISCOVERY_TIMEOUT_S = 1.0


@dataclass
class Discovery:
    """Boards that answered discovery, and Espressif ports that did not.

    Attributes:
        devices: Open adapters of every board that reported its status.
        silent: Espressif USB ports that opened but sent no status.
        unavailable: Espressif USB ports that could not be opened, with the
            reason; an exclusive reader such as a running app makes a port busy.
    """

    devices: list[SerialProvisioningDevice]
    silent: list[str]
    unavailable: dict[str, str]

    def close(self) -> None:
        """Close every opened board."""
        for device in self.devices:
            device.close()


def _probe(connection: Any, timeout: float) -> DeviceStatus | None:
    decoder = SerialFrameStreamDecoder()
    connection.write(encode_serial_frame(TYPE_DISCOVER_REQUEST, b""))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        chunk = connection.read(max(1, getattr(connection, "in_waiting", 0)))
        if not chunk:
            continue
        for frame in decoder.feed(chunk):
            if frame.type == TYPE_DEVICE_STATUS:
                return DeviceStatus.from_payload(frame.payload)
    return None


def discover_boards(timeout: float = DISCOVERY_TIMEOUT_S) -> Discovery:
    """Ask every serial port for a board status without resetting the boards.

    Args:
        timeout: Seconds to wait for each port's status.

    Returns:
        The discovered boards (open; call :meth:`Discovery.close`) and the
        Espressif ports that were busy or silent.

    Raises:
        ProvisioningError: pyserial is not installed.
    """
    try:
        import serial
        from serial.tools import list_ports
    except ImportError as exc:
        raise ProvisioningError("pyserial is required for USB provisioning") from exc

    result = Discovery([], [], {})
    for port in sorted(list_ports.comports(), key=lambda item: item.device):
        espressif = getattr(port, "vid", None) == ESPRESSIF_USB_VID
        try:
            connection = serial.Serial(port.device, 921600, timeout=0.1)
        except Exception as exc:  # noqa: BLE001 — a port that cannot open is reported
            if espressif:
                result.unavailable[port.device] = str(exc) or type(exc).__name__
            continue
        try:
            status = _probe(connection, timeout)
        except Exception:  # noqa: BLE001 — a port that fails discovery is skipped
            status = None
        if status is None:
            try:
                connection.close()
            except AttributeError:
                pass
            if espressif:
                result.silent.append(port.device)
            continue
        result.devices.append(SerialProvisioningDevice(connection, status))
    return result


def _open_serial_devices() -> list[SerialProvisioningDevice]:
    """Return open adapters of every board that answers discovery."""
    return discover_boards().devices
