"""Offline USB reference tests with real serial framing and clock fitting."""

import json
import struct
import time
from queue import Empty, Queue

import pytest

from fall_detection.radio.acquisition.ble_reference import (
    ROUND,
    BleTransmitterReference,
)
from fall_detection.radio.acquisition.serial_framing import (
    SerialFrameStreamDecoder,
    encode_serial_frame,
)

MAC = "02:00:00:00:00:00"


class FakeSerial:
    def __init__(self, *args, **kwargs):
        self.in_waiting = 0
        self.output = Queue()
        self.decoder = SerialFrameStreamDecoder()
        self.boot = 11
        self.drops = 0
        self.closed = False
        self.sensing_phy = "he20"
        self.sensing_version = 3

    def write(self, data):
        for frame in self.decoder.feed(data):
            if frame.type == 5:
                payload = json.dumps(
                    dict(
                        role="transmitter",
                        mac=MAC,
                        ready=True,
                        profile_fingerprint="0123456789abcdef",
                        sensing_phy=self.sensing_phy,
                        sensing_version=self.sensing_version,
                    )
                ).encode()
                self.output.put(encode_serial_frame(6, payload))
            elif frame.payload[:4] == b"CBCK":
                _, identity, t1 = struct.unpack("!4sIQ", frame.payload)
                device = time.monotonic_ns() // 1000 + 1_000_000
                payload = struct.pack(
                    "!4sIQQQII",
                    b"CBCK",
                    identity,
                    t1,
                    device,
                    device,
                    self.boot,
                    self.drops,
                )
                self.output.put(encode_serial_frame(13, payload))
            else:
                self.output.put(encode_serial_frame(13, b"ok"))
        return len(data)

    def read(self, size):
        try:
            return self.output.get(timeout=0.01)
        except Empty:
            return b""

    def close(self):
        self.closed = True


def reference(events):
    return BleTransmitterReference(
        "fake",
        MAC,
        lambda kind, **value: events.append((kind, value)),
        serial_factory=FakeSerial,
        expected_profile_fingerprint="0123456789abcdef",
    )


def test_usb_reference_verifies_identity_maps_clock_and_logs_rounds():
    events = []
    ref = reference(events)
    try:
        ref.start()
        ref.run_id = 123
        for identity in range(4):
            ref.sync(identity)
            time.sleep(0.005)
        assert ref.ready
        device = time.monotonic_ns() // 1000 + 1_000_000
        assert abs(ref.capture_time(device) - time.monotonic_ns()) < 5_000_000
        ref.accept_round(
            ROUND.pack(b"CBRD", 123, 11, 0, device, device, 12500, 15, 0, 0, 1, 2)
        )
        assert events[-1][0] == "round"
        assert events[-1][1]["sequence"] == 0
        assert events[-1][1]["owners"] == [0, 1, 2]
        assert ref.command(b"CBST" + struct.pack("!Q", 123)) == b"ok"
    finally:
        ref.stop()


def test_usb_reference_detects_log_overflow_and_transmitter_restart():
    for failure in ("overflow", "restart"):
        ref = reference([])
        try:
            ref.start()
            ref.sync(0)
            if failure == "overflow":
                ref.connection.drops = 1
            else:
                ref.connection.boot = 12
            with pytest.raises(RuntimeError):
                ref.sync(1)
            assert not ref.ready
        finally:
            ref.stop()


def test_usb_reference_rejects_wrong_profile_before_sensing():
    ref = BleTransmitterReference(
        "fake",
        MAC,
        lambda *a, **k: None,
        serial_factory=FakeSerial,
        expected_profile_fingerprint="ffffffffffffffff",
    )
    try:
        with pytest.raises(RuntimeError, match="profile mismatch"):
            ref.start()
    finally:
        ref.stop()


def test_collection_reference_rejects_diagnostic_phy():
    connection = FakeSerial()
    connection.sensing_phy = "ht20"
    ref = BleTransmitterReference(
        "fake",
        MAC,
        lambda *a, **k: None,
        serial_factory=lambda *a, **k: connection,
        expected_sensing_phy="he20",
    )
    try:
        with pytest.raises(RuntimeError, match="mismatch"):
            ref.start()
    finally:
        ref.stop()


def test_collection_reference_rejects_older_sensing_protocol():
    connection = FakeSerial()
    connection.sensing_version = 2
    ref = BleTransmitterReference(
        "fake",
        MAC,
        lambda *a, **k: None,
        serial_factory=lambda *a, **k: connection,
        expected_sensing_version=3,
    )
    try:
        with pytest.raises(RuntimeError, match="mismatch"):
            ref.start()
    finally:
        ref.stop()


@pytest.mark.parametrize(
    "corruption", [b"\x00\x01x\x00", b"\x00CSI_TX_STATS,1000,0,0,0,0\r\n\x00"]
)
def test_usb_reference_rejects_corrupt_frames_and_missing_round_logs(corruption):
    ref = reference([])
    try:
        ref.start()
        ref.sync(0)
        ref.connection.output.put(corruption)
        deadline = time.monotonic() + 1
        while ref.failure is None and time.monotonic() < deadline:
            time.sleep(0.005)
        assert ref.failure and not ref.log_complete
    finally:
        ref.stop()
    ref = reference([])
    ref.run_id = 123
    with pytest.raises(RuntimeError, match="sequence gap"):
        ref.accept_round(
            ROUND.pack(b"CBRD", 123, 11, 1, 1000, 1000, 12500, 15, 0, 1, 2, 3)
        )
    assert not ref.log_complete


def test_usb_reference_allows_framed_statistics_between_clock_exchanges():
    ref = reference([])
    try:
        ref.start()
        for identity in range(4):
            ref.connection.output.put(
                encode_serial_frame(2, b"CSI_TX_STATS,1000,0,0,0,0")
            )
            ref.sync(identity)
            time.sleep(0.005)
        assert ref.ready and ref.failure is None and ref.log_complete
    finally:
        ref.stop()
