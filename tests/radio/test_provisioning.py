import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
import serial
from serial.tools import list_ports

from fall_detection.radio.acquisition.serial_framing import (
    TYPE_DEVICE_STATUS,
    encode_serial_frame,
)
from fall_detection.radio.profile import RadioInventory, RadioProfile
from fall_detection.radio.provisioning import (
    DeviceStatus,
    ProvisioningError,
    RadioProvisioner,
    _open_serial_devices,
)


class FakeSerialConnection:
    def __init__(self, port: str) -> None:
        self.port = port
        self.is_open = True
        self.dtr = True
        self.rts = True
        self._incoming = bytearray()

    @property
    def in_waiting(self) -> int:
        return len(self._incoming)

    def write(self, _data: bytes) -> int:
        payload = json.dumps(
            {
                "role": "receiver",
                "target": "esp32c5",
                "mac": "44:bd:8d:d0:b1:4c",
                "firmware_version": "2",
                "protocol_version": 2,
                "ready": False,
            }
        ).encode()
        self._incoming.extend(encode_serial_frame(TYPE_DEVICE_STATUS, payload))
        return len(_data)

    def read(self, size: int) -> bytes:
        data = bytes(self._incoming[:size])
        del self._incoming[:size]
        return data

    def close(self) -> None:
        self.is_open = False


def test_open_serial_devices_does_not_close_last_device_after_later_open_failure(
    monkeypatch,
):
    connection = FakeSerialConnection("/dev/ttyACM0")

    def open_serial(port: str, _baud: int, timeout: float):
        assert timeout == 0.1
        if port == "/dev/ttyACM0":
            return connection
        raise serial.SerialException("not a usable serial device")

    monkeypatch.setattr(
        list_ports,
        "comports",
        lambda: [
            SimpleNamespace(device="/dev/ttyACM0"),
            SimpleNamespace(device="/dev/ttyS0"),
        ],
    )
    monkeypatch.setattr(serial, "Serial", open_serial)

    devices = _open_serial_devices()

    assert len(devices) == 1
    assert devices[0].connection.is_open
    devices[0].close()


def test_discovery_preserves_power_and_reset_diagnostics():
    payload = {
        "role": "transmitter",
        "target": "esp32c6",
        "mac": "02:00:00:00:00:00",
        "protocol_version": 2,
        "ready": True,
        "csi_transport": "ble",
        "reset_reason": "brownout",
        "uptime_ms": 1500,
        "radio_active": False,
        "tx_power_quarter_dbm": 44,
    }
    status = DeviceStatus.from_payload(json.dumps(payload).encode())
    assert status.reset_reason == "brownout" and status.uptime_ms == 1500
    assert status.csi_transport == "ble" and status.radio_active is False
    assert status.tx_power_quarter_dbm == 44


class FakeProvisioningDevice:
    def __init__(self, device):
        self.status = DeviceStatus(device.role, device.target, device.mac, "test", 2)
        self.payloads = []
        self.commits = 0
        self.closed = False

    def stage_profile(self, payload):
        self.payloads.append(json.loads(payload))

    def commit_profile(self):
        self.commits += 1
        payload = self.payloads[-1]
        self.status = replace(
            self.status,
            ready=True,
            profile_id=payload["profile"]["profile_id"],
            profile_fingerprint=payload["fingerprint"],
        )

    def refresh_status(self):
        return self.status

    def close(self):
        self.closed = True


@pytest.fixture
def provisioning_setup():
    def device(i):
        return {
            "id": f"board-{i}",
            "role": "transmitter" if i == 0 else "receiver",
            "target": "esp32c6",
            "mac": f"02:00:00:00:00:{i:02x}",
        }

    inventory = RadioInventory.from_mapping(
        {
            "schema_version": 1,
            "transmitter": device(0),
            "receivers": [device(i) for i in range(1, 5)],
        }
    )
    profile = RadioProfile.from_mapping(
        {
            "schema_version": 1,
            "profile_id": "indonesia-2g-ch6-80hz",
            "country_code": "ID",
            "band": "2.4ghz",
            "channel": 6,
            "bandwidth_mhz": 20,
            "nominal_rate_hz": 80,
        }
    )
    return inventory, profile


def test_sequential_provisioning_preserves_full_inventory_on_every_board(
    provisioning_setup,
):
    inventory, profile = provisioning_setup
    boards = [
        FakeProvisioningDevice(device)
        for device in (inventory.transmitter, *inventory.receivers)
    ]
    reports = [
        RadioProvisioner([board]).provision(inventory, profile, sequential=True)
        for board in reversed(boards)
    ]
    assert len({report.fingerprint for report in reports}) == 1
    for board in boards:
        assert board.commits == 1
        assert board.payloads == boards[0].payloads
        assert board.payloads[0]["receivers"] == [d.mac for d in inventory.receivers]
        assert board.payloads[0]["transmitter_mac"] == inventory.transmitter.mac
        assert board.status.ready


@pytest.mark.parametrize("count", [0, 2, 5])
def test_sequential_requires_exactly_one_board(provisioning_setup, count):
    inventory, profile = provisioning_setup
    boards = [FakeProvisioningDevice(inventory.transmitter) for _ in range(count)]
    with pytest.raises(ProvisioningError, match="exactly one"):
        RadioProvisioner(boards).provision(inventory, profile, sequential=True)
    assert all(not board.payloads for board in boards)


@pytest.mark.parametrize(
    "change,match",
    [
        ({"mac": "02:00:00:00:ff:ff"}, "unknown device MAC"),
        ({"target": "esp32c5"}, "role/target"),
        ({"role": "receiver"}, "role/target"),
        ({"protocol_version": 1}, "unsupported protocol"),
    ],
)
def test_sequential_rejects_unverified_identity(provisioning_setup, change, match):
    inventory, profile = provisioning_setup
    board = FakeProvisioningDevice(inventory.transmitter)
    board.status = replace(board.status, **change)
    with pytest.raises(ProvisioningError, match=match):
        RadioProvisioner([board]).provision(inventory, profile, sequential=True)
    assert not board.payloads


def test_default_provisioning_still_requires_all_boards(provisioning_setup):
    inventory, profile = provisioning_setup
    board = FakeProvisioningDevice(inventory.transmitter)
    with pytest.raises(ProvisioningError, match="expected 5 devices"):
        RadioProvisioner([board]).provision(inventory, profile)
    boards = [
        FakeProvisioningDevice(device)
        for device in (inventory.transmitter, *inventory.receivers)
    ]
    report = RadioProvisioner(boards).provision(inventory, profile)
    assert len(report.devices) == 5 and all(board.status.ready for board in boards)


def test_sequential_validates_disconnected_board_capabilities(provisioning_setup):
    inventory, _ = provisioning_setup
    inventory = replace(
        inventory, transmitter=replace(inventory.transmitter, target="esp32c5")
    )
    profile = RadioProfile.from_mapping(
        {
            "schema_version": 1,
            "profile_id": "indonesia-5g-ch44-80hz",
            "country_code": "ID",
            "band": "5ghz",
            "channel": 44,
            "bandwidth_mhz": 20,
            "nominal_rate_hz": 80,
        }
    )
    board = FakeProvisioningDevice(inventory.transmitter)
    with pytest.raises(ProvisioningError, match="5ghz profiles require ESP32-C5"):
        RadioProvisioner([board]).provision(inventory, profile, sequential=True)
    assert not board.payloads


def test_sequential_requires_post_commit_verification(provisioning_setup):
    inventory, profile = provisioning_setup
    board = FakeProvisioningDevice(inventory.receivers[0])
    board.refresh_status = lambda: replace(board.status, ready=False)
    with pytest.raises(ProvisioningError, match="did not complete"):
        RadioProvisioner([board]).provision(inventory, profile, sequential=True)


@pytest.mark.parametrize("command", ["discover", "provision"])
def test_radio_cli_dispatches_arguments_to_operation(command, monkeypatch):
    from fall_detection.radio import provisioning

    calls = []
    monkeypatch.setattr(provisioning, command, lambda argv: calls.append(argv) or 7)
    assert provisioning.main([command, "--example"]) == 7
    assert calls == [["--example"]]


def test_radio_cli_help_and_unknown_command(capsys):
    from fall_detection.radio import provisioning

    with pytest.raises(SystemExit) as help_exit:
        provisioning.main(["--help"])
    assert help_exit.value.code == 0
    assert "discover" in capsys.readouterr().out
    with pytest.raises(SystemExit) as error:
        provisioning.main(["unknown"])
    assert error.value.code == 2


def test_radio_cli_dispatches_transmitter_control(monkeypatch):
    from fall_detection.radio import provisioning, wireless_control

    calls = []
    monkeypatch.setattr(wireless_control, "main", lambda argv: calls.append(argv) or 3)
    assert provisioning.main(["transmitter", "status"]) == 3
    assert calls == [["status"]]
