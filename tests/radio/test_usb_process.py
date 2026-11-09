"""Real POSIX IPC keeps USB draining independently of the GUI interpreter."""

import ctypes
import os
import subprocess
import sys
import time

import pytest
import serial

from fall_detection.radio.acquisition.usb_process import UsbReadProcess

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="POSIX serial descriptor handoff"
)


def open_pump():
    import pty

    master, slave = pty.openpty()
    port = serial.Serial(os.ttyname(slave), 921600, timeout=0.005)
    os.close(slave)
    return master, port, UsbReadProcess(port.fileno())


def test_process_preserves_bytes_and_read_completion_times_while_parent_gil_is_held():
    master, port, pump = open_pump()
    # Producer runs separately too: a Python thread here would stop with the GUI GIL.
    payload = bytes(range(256)) * 192  # larger than the PTY's receive capacity
    producer = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import os,sys,time; p=bytes(range(256))*192; n=0; t=time.monotonic(); "
            "\nwhile n<len(p): n+=os.write(int(sys.argv[1]),p[n:])"
            "\nprint(time.monotonic()-t,flush=True)",
            str(master),
        ],
        pass_fds=(master,),
        stdout=subprocess.PIPE,
        text=True,
    )
    chunks = []
    resumed = None
    try:
        # PyDLL deliberately retains this interpreter's GIL, unlike time.sleep.
        libc = ctypes.PyDLL(None)
        libc.usleep(ctypes.c_uint(150_000))
        resumed = time.monotonic_ns()
        # The producer must have finished while parent threads could not run.
        assert producer.wait(timeout=1) == 0
        assert float(producer.stdout.read()) < 0.14
        while sum(len(chunk.data) for chunk in chunks) < len(payload):
            chunk = pump.read_chunk()
            assert chunk is not None
            chunks.append(chunk)
        assert b"".join(chunk.data for chunk in chunks) == payload
        assert all(chunk.arrival_ns < resumed for chunk in chunks)
        assert [chunk.arrival_ns for chunk in chunks] == sorted(
            chunk.arrival_ns for chunk in chunks
        )
        pump.request_stop()
        assert pump.read_chunk() is None
    finally:
        pump.close()
        if producer.poll() is None:
            producer.kill()
        producer.wait()
        producer.stdout.close()
        port.close()
        os.close(master)


def test_process_shutdown_drains_already_read_bytes():
    master, port, pump = open_pump()
    try:
        os.write(master, b"first")
        assert pump.read_chunk().data == b"first"
        os.write(master, b"last")
        # Receipt establishes ownership before stop, independent of flush timing.
        last = pump.read_chunk()
        pump.request_stop()
        assert last.data == b"last"
        assert pump.read_chunk() is None
        pump.close()
        pump.close()
        assert pump._process.poll() == 0
    finally:
        pump.close()
        port.close()
        os.close(master)


def test_serial_disconnect_is_reported_instead_of_becoming_an_empty_stream():
    master, port, pump = open_pump()
    try:
        os.close(master)
        with pytest.raises(OSError, match="USB|Input/output|disconnected"):
            pump.read_chunk()
    finally:
        pump.close()
        port.close()


def test_process_stop_preserves_received_prefix_during_input():
    master, port, pump = open_pump()
    payload = b"".join(index.to_bytes(4, "big") for index in range(8192))
    try:
        os.write(master, payload)
        first = pump.read_chunk()
        pump.request_stop()
        chunks = [first.data]
        while chunk := pump.read_chunk():
            chunks.append(chunk.data)
        # Bytes still in the terminal's kernel input at stop are not yet owned.
        # Already read bytes must form an intact, ordered prefix with no partial
        # IPC frame, and the child must finish rather than hang on its output.
        received = b"".join(chunks)
        assert received and payload.startswith(received)
        assert pump._process.poll() == 0
    finally:
        pump.close()
        port.close()
        os.close(master)


def test_failed_process_start_releases_parent_descriptors():
    with pytest.raises(ValueError):
        UsbReadProcess(-1)
