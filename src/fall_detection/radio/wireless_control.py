"""One-time USB pairing and connectionless transmitter status/provisioning."""

from __future__ import annotations

import argparse
import json
import secrets
from threading import Event, Lock, Thread
import time
from typing import Any, Callable

from .acquisition.serial_framing import SerialFrameStreamDecoder, encode_serial_frame
from .acquisition.wireless_reference import WirelessReferenceSerial
from .profile import RadioInventory
from .settings import add_config_argument, resolve_settings
from .provisioning import (
    DeviceStatus,
    RadioProvisioner,
    SerialProvisioningDevice,
    ProvisioningError,
)


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
        transmitter_link: str = "ble",
    ) -> None:
        if transmitter_link not in {"ble", "espnow_uart"}:
            raise ValueError("unsupported wireless transmitter link")
        self._prefix = "relay" if transmitter_link == "espnow_uart" else "wireless"
        self._version = 1 if transmitter_link == "espnow_uart" else 2
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
            if (
                transmitter_link == "espnow_uart"
                and self.gateway_status.get("relay_transport") != "espnow_uart"
            ):
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
        except Exception as exc:
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
    transmitter_link: str = "ble",
    channel: int = 6,
) -> None:
    """Verify both identities before storing a fresh shared key over USB.

    Keys are never printed or included in experiment journals. Pairing reboots
    both boards and must be performed with sensing stopped.
    """
    from serial import Serial

    if transmitter_link not in {"ble", "espnow_uart"} or not 1 <= channel <= 13:
        raise ValueError("invalid pairing transport/channel")
    relay = transmitter_link == "espnow_uart"
    if not inventory.gateway or tx_port == gateway_port:
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
            if relay and expected is inventory.transmitter:
                if (raw.get("role"), raw.get("target"), raw.get("relay_version")) != (
                    "relay",
                    "esp32c6",
                    1,
                ):
                    raise ValueError("pairing requires the UART companion C6 USB port")
            elif relay:
                if (
                    raw.get("role"),
                    raw.get("target"),
                    raw.get("mac"),
                    raw.get("relay_version"),
                ) != ("gateway", "esp32c6", expected.mac, 1):
                    raise ValueError("pairing relay gateway identity mismatch")
            elif (
                raw.get("role"),
                raw.get("target"),
                raw.get("mac"),
                raw.get("wireless_version"),
            ) != (expected.role, expected.target, expected.mac, 2):
                raise ValueError("pairing firmware/identity mismatch")
            if raw.get("radio_active") or raw.get("configured"):
                raise ValueError("stop sensing before pairing")
        source_mac = identities[0]["mac"] if relay else inventory.transmitter.mac
        payload = (
            (b"CRPS" if relay else b"CWPS")
            + bytes.fromhex(source_mac.replace(":", ""))
            + bytes.fromhex(inventory.gateway.mac.replace(":", ""))
            + secrets.token_bytes(32)
        )
        if relay:
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


def main(argv: list[str] | None = None) -> int:
    """Pair hardware once, or configure the transmitter through gateway USB."""
    parser = argparse.ArgumentParser(prog="csi-radio transmitter", description=__doc__)
    parser.add_argument("action", choices=("pair", "status", "provision"))
    parser.add_argument("--gateway-port")
    parser.add_argument("--transmitter-link", choices=("ble", "espnow_uart"))
    parser.add_argument("--channel", type=int, help="paired ESP-NOW backhaul channel")
    parser.add_argument(
        "--port", help="initial pairing USB: C5 for BLE, companion C6 for espnow_uart"
    )
    add_config_argument(parser)
    args = parser.parse_args(argv)
    pairing_port = args.port
    try:
        settings = resolve_settings(args)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    inventory = settings.inventory
    if args.transmitter_link == "usb":
        parser.error("wireless control requires espnow_uart or ble transmitter_link")
    if not args.gateway_port:
        parser.error("gateway port is required")
    if args.channel is not None and args.channel != settings.transport.channel:
        parser.error(
            "--channel must match transport.channel in the radio configuration"
        )
    args.channel = settings.transport.channel
    if args.action == "pair":
        # Pairing uses the companion USB port, while USB fallback uses the C5.
        if args.transmitter_link == "espnow_uart" and pairing_port is None:
            args.port = settings.connection.get("companion_port")
        if not args.port:
            parser.error("pair requires --port for the identified source board")
        pair_devices(
            args.port,
            args.gateway_port,
            inventory,
            transmitter_link=args.transmitter_link,
            channel=args.channel,
        )
        source = (
            "companion C6" if args.transmitter_link == "espnow_uart" else "transmitter"
        )
        print(
            f"Paired identified {source} and gateway; keys stored only on the boards."
        )
        return 0
    bridge = GatewayWirelessPort(
        args.gateway_port, transmitter_link=args.transmitter_link
    )
    try:
        if inventory.gateway is None or (
            bridge.gateway_status.get("role"),
            bridge.gateway_status.get("target"),
            bridge.gateway_status.get("mac"),
        ) != ("gateway", "esp32c6", inventory.gateway.mac):
            raise RuntimeError("wireless setup gateway identity mismatch")
        raw = discover_port(bridge.serial, timeout=5)
        if (raw.get("mac"), raw.get("role")) != (
            inventory.transmitter.mac,
            "transmitter",
        ):
            raise RuntimeError("wireless transmitter identity mismatch")
        if args.action == "status":
            print(json.dumps(raw, indent=2))
        else:
            profile = settings.profile
            adapter = WirelessProvisioningDevice(
                bridge.serial,
                DeviceStatus.from_payload(json.dumps(raw).encode()),
                timeout=5,
            )
            report = RadioProvisioner([adapter]).provision(
                inventory, profile, sequential=True
            )
            print("Wireless transmitter profile committed:", report.fingerprint)
    finally:
        bridge.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
