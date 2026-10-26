import json
from types import SimpleNamespace

import serial
from serial.tools import list_ports

from fall_detection.radio.acquisition.serial_framing import (
    TYPE_DEVICE_STATUS,
    encode_serial_frame,
)
from fall_detection.radio.provisioning import _open_serial_devices


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
