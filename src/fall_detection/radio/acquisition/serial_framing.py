"""CRC-protected COBS framing for native USB radio control and CSI batches."""

from __future__ import annotations

from dataclasses import dataclass

from .native import require_native

MAGIC = b"CSIS"
VERSION = 1
TYPE_CSI_PACKET = 1
TYPE_TRANSMITTER_STATS = 2
TYPE_GATEWAY_STATS = 3
TYPE_CLOCK_SYNC = 4
TYPE_DISCOVER_REQUEST = 5
TYPE_DEVICE_STATUS = 6
TYPE_PROFILE_STAGE = 7
TYPE_PROFILE_STAGE_ACK = 8
TYPE_PROFILE_COMMIT = 9
TYPE_PROFILE_COMMIT_ACK = 10
TYPE_CLOCK_SYNC_REQUEST = 11
TYPE_GATEWAY_CONTROL = 20
TYPE_GATEWAY_RESPONSE = 21
TYPE_GATEWAY_ROUND = 22
TYPE_GATEWAY_EVENT = 23
TYPE_GATEWAY_ENVELOPE = 24
TYPE_GATEWAY_ACK = 25
TYPE_WIRELESS_REQUEST = 26
TYPE_WIRELESS_RESPONSE = 27
TYPE_WIRELESS_PAIR = 28
TYPE_WIRELESS_PAIR_ACK = 29
TYPE_RELAY_RECOVER = 31
KNOWN_TYPES = {
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    TYPE_CSI_PACKET,
    TYPE_TRANSMITTER_STATS,
    TYPE_GATEWAY_STATS,
    TYPE_CLOCK_SYNC,
    TYPE_DISCOVER_REQUEST,
    TYPE_DEVICE_STATUS,
    TYPE_PROFILE_STAGE,
    TYPE_PROFILE_STAGE_ACK,
    TYPE_PROFILE_COMMIT,
    TYPE_PROFILE_COMMIT_ACK,
    TYPE_CLOCK_SYNC_REQUEST,
    TYPE_RELAY_RECOVER,
}
MAX_PAYLOAD = 1400


class SerialFrameError(ValueError):
    """Raised when one serial gateway frame is malformed."""


@dataclass(frozen=True)
class SerialFrame:
    """One decoded gateway frame."""

    type: int
    payload: bytes


def encode_serial_frame(frame_type: int, payload: bytes) -> bytes:
    """Encode a gateway frame using the native transport implementation."""
    if frame_type not in KNOWN_TYPES:
        raise SerialFrameError("unknown serial frame type")
    if len(payload) > MAX_PAYLOAD:
        raise SerialFrameError("serial frame payload exceeds 1400 bytes")
    return require_native().encode_frame(frame_type, payload)


def decode_serial_frame(encoded: bytes) -> SerialFrame:
    """Decode a single delimiter-free frame using the native implementation."""
    decoder = require_native().FrameDecoder()
    frames = decoder.feed(b"\x00" + encoded + b"\x00")
    if decoder.malformed_frames or decoder.oversized_frames or len(frames) != 1:
        raise SerialFrameError("invalid serial frame")
    return SerialFrame(*frames[0])


class SerialFrameStreamDecoder:
    """Decode incoming serial frames using the native transport layer."""

    def __init__(self) -> None:
        self._native = require_native().FrameDecoder()
        self.malformed_frames = 0
        self.oversized_frames = 0

    def feed(self, data: bytes) -> list[SerialFrame]:
        """Consume bytes and return every complete valid frame."""
        values = self._native.feed(data)
        self.malformed_frames = self._native.malformed_frames
        self.oversized_frames = self._native.oversized_frames
        return [SerialFrame(kind, payload) for kind, payload in values]
