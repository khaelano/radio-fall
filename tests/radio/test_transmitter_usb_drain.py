"""USB draining must progress while reference event handling is delayed."""

import json
import pytest
from queue import Empty, Queue
from threading import Event

from fall_detection.radio.acquisition import transmitter_reference as reference_module
from fall_detection.radio.acquisition.serial_framing import (
    SerialFrameStreamDecoder,
    encode_serial_frame,
)
from fall_detection.radio.acquisition.transmitter_reference import (
    ROUND,
    TransmitterReference,
)

MAC = "02:00:00:00:00:00"


class ReferenceSerial:
    def __init__(self):
        self.output = Queue()
        self.in_waiting = 0
        self.decoder = SerialFrameStreamDecoder()
        self.drained = Event()
        self.last_chunk = None
        self.closed = False

    def write(self, data):
        for frame in self.decoder.feed(data):
            if frame.type == 5:
                status = dict(
                    role="transmitter",
                    mac=MAC,
                    ready=True,
                    protocol_version=3,
                    csi_transport="espnow_gateway",
                )
                self.output.put(encode_serial_frame(6, json.dumps(status).encode()))
        return len(data)

    def read(self, size):
        try:
            chunk = self.output.get(timeout=0.01)
        except Empty:
            return b""
        if chunk == self.last_chunk:
            self.drained.set()
        return chunk

    def close(self):
        self.closed = True


def round_frame(sequence):
    return encode_serial_frame(
        22,
        ROUND.pack(
            b"CGRD",
            123,
            11,
            sequence,
            1000 + sequence * 8333,
            1000 + sequence * 8333,
            8333,
            15,
            0,
            255,
            255,
            255,
        ),
    )


def test_usb_is_drained_while_round_journal_is_blocked():
    serial = ReferenceSerial()
    entered, release, accepted = Event(), Event(), []

    def sink(kind, **values):
        if kind != "round":
            return
        if values["sequence"] == 0:
            entered.set()
            release.wait(2)
        accepted.append(values["sequence"])

    ref = TransmitterReference(
        "fake",
        MAC,
        sink,
        serial_factory=lambda *a, **k: serial,
        expected_sensing_rate_hz=120,
    )
    ref.run_id = 123
    try:
        ref.start()
        serial.output.put(round_frame(0))
        assert entered.wait(1)
        serial.last_chunk = round_frame(32)
        for seq in range(1, 33):
            serial.output.put(round_frame(seq))
        assert serial.drained.wait(0.5), "event processing prevents USB draining"
        assert accepted == []  # The journal really is still blocked.
        release.set()
        serial.output.put(round_frame(33))
        # A second callback provides deterministic completion without sleeps.
        finished = Event()
        original_sink = ref.event_sink

        def finish(kind, **values):
            original_sink(kind, **values)
            if kind == "round" and values["sequence"] == 34:
                finished.set()

        ref.event_sink = finish
        serial.output.put(round_frame(34))
        assert finished.wait(1)
        assert accepted == list(range(35))
        assert ref.failure is None
    finally:
        release.set()
        ref.stop()
    assert serial.closed


def test_usb_read_queue_overflow_is_explicit(monkeypatch):
    monkeypatch.setattr(reference_module, "USB_READ_QUEUE_CHUNKS", 2)
    serial = ReferenceSerial()
    entered, release, failed = Event(), Event(), Event()

    def sink(kind, **values):
        if kind == "round" and values["sequence"] == 0:
            entered.set()
            release.wait(2)

    ref = TransmitterReference(
        "fake",
        MAC,
        sink,
        serial_factory=lambda *a, **k: serial,
        failure_sink=lambda message: failed.set(),
        expected_sensing_rate_hz=120,
    )
    ref.run_id = 123
    try:
        ref.start()
        serial.output.put(round_frame(0))
        assert entered.wait(1)
        for seq in range(1, 5):
            serial.output.put(round_frame(seq))
        assert failed.wait(1)
        assert ref.failure == "transmitter USB receive queue overflow"
        assert not ref.log_complete
    finally:
        release.set()
        ref.stop()


def test_rejected_round_keeps_wire_evidence_and_first_failure():
    events = []
    ref = TransmitterReference(
        "unused",
        MAC,
        lambda kind, **values: events.append((kind, values)),
        expected_sensing_rate_hz=120,
    )
    ref.run_id = 123
    decoder = SerialFrameStreamDecoder()
    first = decoder.feed(round_frame(0))[0].payload
    rejected = decoder.feed(round_frame(2))[0].payload
    ref.accept_round(first)
    with pytest.raises(RuntimeError, match="unexplained sequence gap"):
        ref.accept_round(rejected)
    kind, evidence = events[-1]
    assert kind == "transmitter_round_rejected"
    assert evidence["expected_sequence"] == 1
    assert evidence["received_sequence"] == 2
    assert evidence["payload_hex"] == rejected.hex()
    assert evidence["lifetime_log_drops"] == 0
    ref._fail("secondary shutdown error")
    assert ref.failure == "transmitter round log has an unexplained sequence gap"
