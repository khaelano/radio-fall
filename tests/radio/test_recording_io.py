"""Recording producers batch I/O without waiting for storage."""

import os
import ctypes
import time

import pytest

from fall_detection.radio.acquisition.recording_io import RecordingIO


def test_records_stay_in_memory_until_flush_and_preserve_order(tmp_path):
    writer = RecordingIO(interval_s=60, capacity_bytes=128)
    stream = writer.open(tmp_path / "rows.txt", "x")
    try:
        stream.write("one\n")
        stream.flush()
        stream.write("two\n")
        assert (tmp_path / "rows.txt").read_bytes() == b""
        assert writer.pending_bytes == 8
        writer.flush()
        assert (tmp_path / "rows.txt").read_text() == "one\ntwo\n"
        assert writer.pending_bytes == 0
    finally:
        writer.close()


def test_periodic_flush_and_close_drain(tmp_path):
    writer = RecordingIO(interval_s=0.03)
    stream = writer.open(tmp_path / "data.bin", "xb")
    stream.write(b"first")
    until = time.monotonic() + 1
    while not (tmp_path / "data.bin").read_bytes() and time.monotonic() < until:
        time.sleep(0.005)
    assert (tmp_path / "data.bin").read_bytes() == b"first"
    stream.write(b"last")
    writer.close()
    assert (tmp_path / "data.bin").read_bytes() == b"firstlast"
    assert stream.saved


@pytest.mark.skipif(os.name != "posix", reason="GIL-holding libc call")
def test_native_storage_flush_continues_while_python_holds_gil(tmp_path):
    writer = RecordingIO(interval_s=0.03)
    path = tmp_path / "data.bin"
    stream = writer.open(path, "xb")
    try:
        stream.write(b"accepted")
        ctypes.PyDLL(None).usleep(ctypes.c_uint(100000))
        assert writer.pending_bytes == 0
        assert path.read_bytes() == b"accepted"
        assert writer.stats()["backend"] == "rust"
    finally:
        writer.close()


@pytest.mark.skipif(os.name != "posix", reason="native POSIX FIFO backpressure")
def test_slow_storage_does_not_block_ingestion_and_owned_bytes_remain_bounded(tmp_path):
    fifo = tmp_path / "blocked.fifo"
    os.mkfifo(fifo)
    read_fd = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
    payload = b"x" * (2 * 1024 * 1024)
    writer = RecordingIO(interval_s=60, capacity_bytes=len(payload) + 16)
    stream = writer.open(fifo, "a")
    received = bytearray()
    try:
        stream.write(payload)
        with pytest.raises(TimeoutError):
            writer.flush(timeout=0.03)
        other = writer.open(tmp_path / "next.bin", "xb")
        other.write(b"next")
        assert writer.pending_bytes == len(payload) + 4
        with pytest.raises(BufferError):
            other.write(b"x" * 13)
        stream.close()
        deadline = time.monotonic() + 3
        while len(received) < len(payload) and time.monotonic() < deadline:
            try:
                received.extend(os.read(read_fd, 65536))
            except BlockingIOError:
                time.sleep(0.001)
        assert received == payload
        writer.flush()
    finally:
        deadline = time.monotonic() + 3
        while writer.pending_bytes and time.monotonic() < deadline:
            try:
                os.read(read_fd, 65536)
            except BlockingIOError:
                time.sleep(0.001)
        writer.close()
        os.close(read_fd)
    assert (tmp_path / "next.bin").read_bytes() == b"next"


@pytest.mark.skipif(not os.path.exists("/dev/full"), reason="kernel ENOSPC test device")
def test_storage_failure_is_sticky_and_reported():
    writer = RecordingIO(interval_s=60)
    stream = writer.open(__import__("pathlib").Path("/dev/full"), "a")
    stream.write(b"raw")
    with pytest.raises(OSError, match="space"):
        writer.flush()
    with pytest.raises(OSError, match="space"):
        stream.write(b"late")
    with pytest.raises(OSError, match="space"):
        writer.close()
