"""CRC-protected COBS framing for native USB radio control and CSI batches."""

from __future__ import annotations

from dataclasses import dataclass
import struct
import zlib
from .native import core as _core


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
TYPE_BLE_CONTROL = 12
TYPE_BLE_RESPONSE = 13
TYPE_BLE_ROUND = 14
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
    TYPE_BLE_CONTROL,
    TYPE_BLE_RESPONSE,
    TYPE_BLE_ROUND,
    TYPE_RELAY_RECOVER,
}
MAX_PAYLOAD = 1400
HEADER = struct.Struct("!4sBBH")
CRC = struct.Struct("!I")
MAX_RAW_SIZE = HEADER.size + MAX_PAYLOAD + CRC.size
MAX_ENCODED_SIZE = MAX_RAW_SIZE + MAX_RAW_SIZE // 254 + 1


class SerialFrameError(ValueError):
    """Raised when one serial gateway frame is malformed."""


@dataclass(frozen=True)
class SerialFrame:
    """One decoded gateway frame."""

    type: int
    payload: bytes


def cobs_encode(data: bytes) -> bytes:
    """Encode bytes with Consistent Overhead Byte Stuffing."""

    output = bytearray(b"\x00")
    code_index = 0
    code = 1
    for value in data:
        if value == 0:
            output[code_index] = code
            code_index = len(output)
            output.append(0)
            code = 1
            continue
        output.append(value)
        code += 1
        if code == 0xFF:
            output[code_index] = code
            code_index = len(output)
            output.append(0)
            code = 1
    output[code_index] = code
    return bytes(output)


def cobs_decode(data: bytes) -> bytes:
    """Decode one delimiter-free COBS payload."""

    if not data or b"\x00" in data:
        raise SerialFrameError("invalid COBS payload")
    output = bytearray()
    index = 0
    while index < len(data):
        code = data[index]
        index += 1
        if code == 0:
            raise SerialFrameError("zero COBS code")
        end = index + code - 1
        if end > len(data):
            raise SerialFrameError("truncated COBS block")
        output.extend(data[index:end])
        index = end
        if code != 0xFF and index < len(data):
            output.append(0)
    return bytes(output)


def encode_serial_frame(frame_type: int, payload: bytes) -> bytes:
    """Encode one typed gateway frame, including synchronization delimiters."""

    if frame_type not in KNOWN_TYPES:
        raise SerialFrameError("unknown serial frame type")
    if len(payload) > MAX_PAYLOAD:
        raise SerialFrameError("serial frame payload exceeds 1400 bytes")
    if _core is not None and hasattr(_core, "encode_frame"):
        return _core.encode_frame(frame_type, payload)
    header = HEADER.pack(MAGIC, VERSION, frame_type, len(payload))
    body = header + payload
    raw = body + CRC.pack(zlib.crc32(body) & 0xFFFFFFFF)
    return b"\x00" + cobs_encode(raw) + b"\x00"


def decode_serial_frame(encoded: bytes) -> SerialFrame:
    """Decode and validate one delimiter-free gateway frame."""

    if len(encoded) > MAX_ENCODED_SIZE:
        raise SerialFrameError("encoded serial frame is too large")
    raw = cobs_decode(encoded)
    if len(raw) < HEADER.size + CRC.size:
        raise SerialFrameError("serial frame is shorter than its envelope")
    magic, version, frame_type, payload_length = HEADER.unpack_from(raw)
    if magic != MAGIC or version != VERSION:
        raise SerialFrameError("unsupported serial frame magic or version")
    if frame_type not in KNOWN_TYPES:
        raise SerialFrameError("unknown serial frame type")
    if payload_length > MAX_PAYLOAD:
        raise SerialFrameError("serial frame payload exceeds 1400 bytes")
    expected_length = HEADER.size + payload_length + CRC.size
    if len(raw) != expected_length:
        raise SerialFrameError("serial frame length does not match its header")
    body = raw[: -CRC.size]
    (received_crc,) = CRC.unpack_from(raw, len(body))
    if received_crc != (zlib.crc32(body) & 0xFFFFFFFF):
        raise SerialFrameError("serial frame CRC mismatch")
    return SerialFrame(frame_type, raw[HEADER.size : len(body)])


class SerialFrameStreamDecoder:
    """Incrementally recover COBS frames from an arbitrary serial byte stream."""

    def __init__(self) -> None:
        self._native = _core.FrameDecoder() if _core is not None else None
        self._pending = bytearray()
        self._synchronized = False
        self._dropping = False
        self.malformed_frames = 0
        self.oversized_frames = 0

    def feed(self, data: bytes) -> list[SerialFrame]:
        """Consume bytes and return every complete valid frame."""

        if self._native is not None:
            values = self._native.feed(data)
            self.malformed_frames = self._native.malformed_frames
            self.oversized_frames = self._native.oversized_frames
            return [SerialFrame(kind, payload) for kind, payload in values]

        frames: list[SerialFrame] = []
        for value in data:
            if value == 0:
                if not self._synchronized:
                    self._synchronized = True
                    self._pending.clear()
                    self._dropping = False
                    continue
                if self._dropping:
                    self._dropping = False
                    self._pending.clear()
                    continue
                if not self._pending:
                    continue
                try:
                    frames.append(decode_serial_frame(bytes(self._pending)))
                except SerialFrameError:
                    self.malformed_frames += 1
                self._pending.clear()
                continue

            if not self._synchronized or self._dropping:
                continue
            self._pending.append(value)
            if len(self._pending) > MAX_ENCODED_SIZE:
                self.oversized_frames += 1
                self._pending.clear()
                self._dropping = True
        return frames
