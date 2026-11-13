"""Scripted stand-in for ``NativeAcquisition``; no serial device is opened."""

import json
from threading import Lock
from typing import ClassVar

from test_gateway import batch

from fall_detection import _radio_native as core


def native_record(sequence=1, receiver=0):
    """Return a Rust-decoded record built from an independent wire fixture."""
    return core.decode_envelope(
        batch(seq=sequence, receiver=receiver).encode()
    ).records[0]


def item(sequence=1, slot=0, *, run=123, capture_ns=5_000, arrival_ns=6_000):
    """Return one polled tuple in the binding's field order."""
    return (
        native_record(sequence, slot),
        slot,
        run,
        11,
        21,
        sequence,
        capture_ns,
        arrival_ns,
        arrival_ns + 10,
        12.5,
    )


def running_health(*, now_ns=10_000_000_000, status_age_ns=0, record_age_ns=0):
    """Return health for a running run with fresh evidence from four receivers."""
    return {
        "monotonic_ns": now_ns,
        "session": {
            "state": "running",
            "run": "123",
            "clock": {"ready": True, "uncertainty_us": 40.0},
            "gateway": {"configured": True, "received": 400, "forwarded": 399},
            "gateway_age_ns": 0,
            "receivers": [
                {"slot": slot, "status_age_ns": status_age_ns, "status": {"state": 0}}
                for slot in range(4)
            ],
        },
        "run": "123",
        "runs": 1,
        "restarts": 0,
        "failure": None,
        "fatal": False,
        "finished": False,
        "queue": {"pending": 0, "peak": 0, "capacity": 65536},
        "receivers": [
            {"records": 1, "last_record_age_ns": record_age_ns} for _ in range(4)
        ],
        "totals": {"records": 4, "batches": 4},
    }


class FakeAcquisition:
    """Record configuration and lifecycle calls; serve scripted records and health."""

    instances: ClassVar[list] = []

    def __init__(self, config_json):
        self.config = json.loads(config_json)
        self.items = []
        self.health_value = {"session": {"state": "starting_radio"}, "runs": 0}
        self.availability_value = None
        self.started = 0
        self.stopped = 0
        self.stop_error = None
        self._lock = Lock()
        FakeAcquisition.instances.append(self)

    def start(self):
        self.started += 1

    def poll(self, maximum):
        with self._lock:
            values, self.items = self.items[:maximum], self.items[maximum:]
        return values

    def push(self, *values):
        with self._lock:
            self.items.extend(values)

    def health(self):
        return json.dumps(self.health_value)

    def availability(self, seconds):
        return self.availability_value

    def stop(self, timeout):
        self.stopped += 1
        if self.stop_error is not None:
            raise self.stop_error
