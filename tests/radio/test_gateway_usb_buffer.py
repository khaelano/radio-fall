"""Gateway USB must drain during slow storage, with bounded batch ownership."""

from threading import Event
import time

import pytest

from test_gateway import FakeUsb, batch, manager


class DrainUsb(FakeUsb):
    def __init__(self):
        super().__init__()
        self.drained = Event()
        self.track_drain = False

    def read(self, n):
        with self.condition:
            data = super().read(n)
            if data and self.track_drain and not self.pending:
                self.drained.set()
            return data


def test_gateway_drains_usb_while_storage_is_blocked_and_keeps_arrival_time(tmp_path):
    entered, release, finished = Event(), Event(), Event()
    seen = []

    def store(record, arrival_ns):
        if record.sequence == 1:
            entered.set()
            release.wait(2)
        seen.append((record.sequence, arrival_ns))
        if record.sequence == 3:
            finished.set()

    m = manager(tmp_path, store)
    usb = DrainUsb()
    m.serial_factory = lambda *args, **kwargs: usb
    try:
        m._open_gateway()
        usb.inject(24, batch(seq=1).encode())
        assert entered.wait(1)
        with usb.condition:
            usb.inject(24, batch(seq=2).encode())
            usb.inject(24, batch(seq=3).encode())
            usb.track_drain = True
        assert usb.drained.wait(0.5), "storage prevents gateway USB draining"
        released_ns = time.monotonic_ns()
        release.set()
        assert finished.wait(1)
        assert [seq for seq, _ in seen] == [1, 2, 3]
        assert seen[1][1] < released_ns and seen[2][1] < released_ns
        assert m.failure is None
    finally:
        release.set()
        stop = getattr(m, "_stop_gateway_usb", None)
        if stop:
            stop()
        else:
            m._usb_stop.set()
            if m._usb_thread:
                m._usb_thread.join(2)
            if m.connection:
                m.connection.close()
        m.journal.close()


def test_raw_buffer_takes_available_chunks_without_waiting_for_full_batch():
    from fall_detection.radio.acquisition.usb_buffer import UsbReadBuffer

    clock = [1000]
    buffer = UsbReadBuffer(clock_ns=lambda: clock[0])
    buffer.put(b"one", 900)
    buffer.put(b"two", 950)
    result = buffer.get_batch(max_chunks=4, timeout_s=0)
    assert [(chunk.data, chunk.arrival_ns) for chunk in result] == [
        (b"one", 900),
        (b"two", 950),
    ]
    assert buffer.stats()["queued_bytes"] == 0
    assert buffer.stats()["maximum_wait_ns"] == 100


@pytest.mark.parametrize("bytes_limit,chunk_limit", [(5, 2), (100, 1)])
def test_raw_buffer_overflow_preserves_pending_bytes(bytes_limit, chunk_limit):
    from fall_detection.radio.acquisition.usb_buffer import UsbReadBuffer

    buffer = UsbReadBuffer(capacity_bytes=bytes_limit, capacity_chunks=chunk_limit)
    now = time.monotonic_ns()
    buffer.put(b"abcd", now)
    with pytest.raises(BufferError, match="overflow"):
        buffer.put(b"xx", now)
    result = buffer.get_batch(timeout_s=0)
    assert [chunk.data for chunk in result] == [b"abcd"]


def test_raw_buffer_rejects_stale_work_without_deleting_it():
    from fall_detection.radio.acquisition.usb_buffer import UsbReadBuffer

    clock = [10]
    buffer = UsbReadBuffer(maximum_age_ns=100, clock_ns=lambda: clock[0])
    buffer.put(b"raw", 10)
    clock[0] = 111
    with pytest.raises(TimeoutError, match="age"):
        buffer.get_batch(timeout_s=0)
    assert buffer.stats()["queued_bytes"] == 3


def test_raw_buffer_close_drains_existing_chunks_and_rejects_new_work():
    from fall_detection.radio.acquisition.usb_buffer import UsbReadBuffer

    buffer = UsbReadBuffer()
    buffer.put(b"raw", time.monotonic_ns())
    buffer.close()
    assert [chunk.data for chunk in buffer.get_batch(timeout_s=0)] == [b"raw"]
    assert buffer.get_batch(timeout_s=0) == ()
    with pytest.raises(RuntimeError, match="closed"):
        buffer.put(b"late", time.monotonic_ns())


def test_batched_ingestion_never_acknowledges_failed_recording(tmp_path):
    failed = Event()
    seen = []

    def store(record, arrival):
        if record.sequence == 2:
            raise OSError("disk full")
        seen.append(record.sequence)

    m = manager(tmp_path, store)
    m.on_status = lambda message, live: failed.set() if not live else None
    usb = DrainUsb()
    m.serial_factory = lambda *args, **kwargs: usb
    try:
        m._open_gateway()
        with usb.condition:
            usb.inject(24, batch(seq=1).encode())
            usb.inject(24, batch(seq=2).encode())
        assert failed.wait(1)
        assert seen == [1]
        assert "disk full" in m.failure
        assert len([frame for frame in usb.writes if frame.type == 25]) == 1
    finally:
        m._stop_gateway_usb()
        m.journal.close()


def test_gateway_buffer_age_failure_never_acknowledges_data(tmp_path):
    failed = Event()
    seen = []
    m = manager(tmp_path, lambda *args: seen.append(args))
    m.on_status = lambda message, live: failed.set() if not live else None
    usb = DrainUsb()
    m.serial_factory = lambda *args, **kwargs: usb
    try:
        m._open_gateway()
        m._usb_buffer._clock_ns = lambda: time.monotonic_ns() + 1_000_000_000
        usb.inject(24, batch().encode())
        assert failed.wait(1)
        assert "buffer age exceeded" in m.failure
        assert not seen
        assert not [frame for frame in usb.writes if frame.type == 25]
    finally:
        m._stop_gateway_usb()
        m.journal.close()


def test_usb_shutdown_finishes_already_read_data(tmp_path):
    entered, release, finished = Event(), Event(), Event()
    seen = []

    def store(record, arrival):
        if record.sequence == 1:
            entered.set()
            release.wait(2)
        seen.append(record.sequence)
        if record.sequence == 3:
            finished.set()

    m = manager(tmp_path, store)
    usb = DrainUsb()
    m.serial_factory = lambda *args, **kwargs: usb
    try:
        m._open_gateway()
        usb.inject(24, batch(seq=1).encode())
        assert entered.wait(1)
        with usb.condition:
            usb.inject(24, batch(seq=2).encode())
            usb.inject(24, batch(seq=3).encode())
            usb.track_drain = True
        assert usb.drained.wait(0.5)
        release.set()
        m._stop_gateway_usb()
        assert finished.is_set() and seen == [1, 2, 3]
        assert usb.closed
        assert not m._usb_thread.is_alive()
        assert not m._usb_drain_thread.is_alive()
    finally:
        release.set()
        m._stop_gateway_usb()
        m.journal.close()


def test_preview_pauses_for_aged_usb_work_and_resumes_after_it_drains(tmp_path):
    from fall_detection.radio.acquisition.usb_buffer import UsbReadBuffer

    clock = [1_000_000_000]
    m = manager(tmp_path, lambda *args: None)
    m._usb_buffer = UsbReadBuffer(clock_ns=lambda: clock[0])
    try:
        m._usb_buffer.put(b"waiting-for-ingestion", clock[0])
        assert m.preview_ready
        clock[0] += 30_000_000
        assert not m.preview_ready  # one old chunk needs priority over another plot
        assert m.clock_sync_ready and m.failure is None
        assert m._usb_buffer.maximum_age_ns == 200_000_000
        assert m._usb_buffer.get_batch(timeout_s=0)[0].data == b"waiting-for-ingestion"
        assert m.preview_ready
    finally:
        m.journal.close()
