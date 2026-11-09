"""Bounded transmitter serial interface multiplexed through the C6 USB gateway."""

from __future__ import annotations

from threading import Condition
import time
import struct
from typing import Callable

from .serial_framing import (
    SerialFrameStreamDecoder,
    TYPE_WIRELESS_REQUEST,
    encode_serial_frame,
)


class WirelessReferenceSerial:
    """Reuse strict reference validation over a reliable gateway bridge.

    Gateway acceptance of a request is not transmitter execution. Responses and
    authoritative round logs must traverse the bridge before readers see them.
    """

    def __init__(self, write: Callable[[int, bytes], None], capacity: int = 262144):
        self._write = write
        self._capacity = capacity
        self._buffer = bytearray()
        self._condition = Condition()
        self._closed = False
        self._decoder = SerialFrameStreamDecoder()

    @property
    def in_waiting(self) -> int:
        """Return buffered reference bytes without reading the gateway directly."""
        with self._condition:
            return len(self._buffer)

    def feed(self, payload: bytes) -> None:
        """Accept one demultiplexed response, preserving original serial framing."""
        if not payload:
            raise ValueError("empty wireless reference response")
        if payload[0]:
            framed = encode_serial_frame(payload[0], payload[1:])
        else:
            pieces = []
            offset = 1
            while offset < len(payload):
                if len(payload) - offset < 3:
                    raise ValueError("truncated wireless reference batch")
                kind, size = struct.unpack_from("!BH", payload, offset)
                offset += 3
                if not kind or size > len(payload) - offset:
                    raise ValueError("invalid wireless reference batch")
                pieces.append(
                    encode_serial_frame(kind, payload[offset : offset + size])
                )
                offset += size
            if not pieces:
                raise ValueError("empty wireless reference batch")
            framed = b"".join(pieces)
        with self._condition:
            if self._closed:
                return
            if len(self._buffer) + len(framed) > self._capacity:
                raise BufferError("wireless reference queue overflow")
            self._buffer.extend(framed)
            self._condition.notify_all()

    def write(self, data: bytes) -> int:
        """Submit complete requests; the firmware owns reliable radio delivery."""
        if self._closed:
            raise OSError("wireless reference closed")
        for frame in self._decoder.feed(data):
            if len(frame.payload) + 3 >= 1280:
                raise ValueError("wireless command exceeds bridge limit")
            self._write(TYPE_WIRELESS_REQUEST, bytes([frame.type]) + frame.payload)
        return len(data)

    def read(self, size: int) -> bytes:
        """Return available data, waiting at most the serial-compatible 100 ms."""
        deadline = time.monotonic() + 0.1
        with self._condition:
            while not self._buffer and not self._closed:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return b""
                self._condition.wait(remaining)
            count = min(max(size, 0), len(self._buffer))
            data = bytes(self._buffer[:count])
            del self._buffer[:count]
            return data

    def close(self) -> None:
        """Wake readers without closing the shared gateway USB connection."""
        with self._condition:
            self._closed = True
            self._condition.notify_all()
