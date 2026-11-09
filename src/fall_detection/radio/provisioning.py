"""USB discovery and radio-profile provisioning for groups or individual boards.

The host speaks one small framed JSON control protocol to both transmitter
and receiver firmware.  The transport adapter is deliberately separate from
profile validation so validation and commit semantics can be tested without
physical USB boards.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Protocol

from .acquisition.serial_framing import (
    TYPE_DEVICE_STATUS,
    TYPE_DISCOVER_REQUEST,
    TYPE_PROFILE_COMMIT,
    TYPE_PROFILE_COMMIT_ACK,
    TYPE_PROFILE_STAGE,
    TYPE_PROFILE_STAGE_ACK,
    SerialFrameStreamDecoder,
    encode_serial_frame,
)
from .profile import (
    RadioInventory,
    RadioProfile,
    RadioProfileError,
    profile_fingerprint,
)


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
    def from_payload(cls, payload: bytes) -> "DeviceStatus":
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
        if inventory.gateway:
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
            if status.protocol_version not in ((3,) if inventory.gateway else (2, 3)):
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


def _open_serial_devices() -> list[SerialProvisioningDevice]:
    try:
        import serial
        from serial.tools import list_ports
    except ImportError as exc:
        raise ProvisioningError("pyserial is required for USB provisioning") from exc

    devices: list[SerialProvisioningDevice] = []
    for port in sorted(list_ports.comports(), key=lambda item: item.device):
        connection = None
        try:
            connection = serial.Serial(port.device, 921600, timeout=0.1)
            decoder = SerialFrameStreamDecoder()
            connection.write(encode_serial_frame(TYPE_DISCOVER_REQUEST, b""))
            deadline = time.monotonic() + 1.0
            status: DeviceStatus | None = None
            while time.monotonic() < deadline and status is None:
                chunk = connection.read(max(1, getattr(connection, "in_waiting", 0)))
                if not chunk:
                    continue
                for frame in decoder.feed(chunk):
                    if frame.type == TYPE_DEVICE_STATUS:
                        status = DeviceStatus.from_payload(frame.payload)
                        break
            if status is None:
                connection.close()
                continue
            devices.append(SerialProvisioningDevice(connection, status))
        except Exception:
            if connection is not None:
                try:
                    connection.close()
                except AttributeError:
                    pass
    return devices


def configure_connected_devices(
    inventory: RadioInventory,
    profile: RadioProfile,
    *,
    reboot_wait_s: float = 0.6,
    log: Callable[[str], None] | None = None,
) -> tuple[str, ...]:
    """Push ``profile`` to connected boards that are not already running it.

    This is what lets the viewer and the collector configure the radios
    themselves instead of requiring a separate provisioning step.  Only boards
    present in ``inventory`` are touched, so an unplugged transmitter is simply
    skipped.  Boards reboot on commit, hence the wait before the caller
    re-discovers them.  Returns the MACs that were reconfigured.
    """

    expected = {inventory.transmitter.mac: inventory.transmitter}
    expected.update({device.mac: device for device in inventory.receivers})
    expected_fingerprint = profile_fingerprint(profile, inventory)
    payload = _profile_payload(inventory, profile, expected_fingerprint)

    devices = _open_serial_devices()
    stale = [
        device
        for device in devices
        if device.status.mac in expected
        and device.status.profile_fingerprint != expected_fingerprint
    ]
    configured: list[str] = []
    try:
        # Stage everything first so a rejected stage leaves every board alone.
        for device in stale:
            device.stage_profile(payload)
        for device in stale:
            device.commit_profile()
            configured.append(device.status.mac)
            if log is not None:
                log(f"configured {device.status.role} {device.status.mac}")
    finally:
        for device in devices:
            device.close()
    if configured:
        time.sleep(reboot_wait_s)
    return tuple(configured)


def discover(argv: list[str] | None = None) -> int:
    """CLI entry point for USB device discovery."""

    import argparse

    parser = argparse.ArgumentParser(
        prog="csi-radio discover", description="Discover CSI radio boards over USB"
    )
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )
    args = parser.parse_args(argv)
    try:
        devices = _open_serial_devices()
    except ProvisioningError as exc:
        parser.error(str(exc))
    values = [
        {
            **device.status.__dict__,
            "usb_port": getattr(device.connection, "port", None),
        }
        for device in devices
    ]
    for device in devices:
        device.close()
    if args.json:
        print(json.dumps(values, indent=2, sort_keys=True))
    else:
        for value in values:
            print(
                f"{value['role']} {value['mac']} target={value['target']} "
                f"port={value['usb_port'] or '?'} firmware={value['firmware_version']} "
                f"protocol={value['protocol_version']} "
                f"profile={value['profile_id'] or 'unprovisioned'} "
                f"fingerprint={value['profile_fingerprint'] or '-'}"
            )
    return 0


def provision(argv: list[str] | None = None) -> int:
    """CLI entry point for profile provisioning."""

    import argparse

    parser = argparse.ArgumentParser(
        prog="csi-radio provision", description="Provision a selectable CSI radio profile"
    )
    from .settings import add_config_argument, resolve_settings

    add_config_argument(parser)
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="provision exactly one connected registered board using the complete inventory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and print the profile without opening USB devices",
    )
    args = parser.parse_args(argv)
    try:
        settings = resolve_settings(args)
        inventory, profile = settings.inventory, settings.profile
        fingerprint = settings.profile_fingerprint
        if args.dry_run:
            print(
                json.dumps(
                    {
                        "profile_id": profile.profile_id,
                        "band": profile.band,
                        "channel": profile.channel,
                        "fingerprint": fingerprint,
                        "devices": len(inventory.receivers) + 1,
                        "provisioning_mode": "sequential" if args.sequential else "all",
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        devices = _open_serial_devices()
        try:
            report = RadioProvisioner(devices).provision(
                inventory, profile, sequential=args.sequential
            )
        finally:
            for device in devices:
                device.close()
    except (ValueError, OSError, ProvisioningError) as exc:
        parser.error(str(exc))
    print(f"provisioned {report.profile_id} fingerprint={report.fingerprint}")
    if args.sequential:
        print(
            f"verified device {report.devices[0].mac}; "
            "other configured boards were not checked"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Dispatch radio discovery, provisioning and transmitter control."""
    import argparse
    import sys

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "transmitter":
        from .wireless_control import main as transmitter_main

        return transmitter_main(arguments[1:])
    actions = {"discover": discover, "provision": provision}
    if arguments and arguments[0] in actions:
        return actions[arguments[0]](arguments[1:])
    parser = argparse.ArgumentParser(description="Manage CSI radios")
    parser.add_argument("command", choices=(*actions, "transmitter"), help="radio operation")
    parser.parse_args(arguments)
    return 2
