"""Complete ESP-NOW/USB envelopes and host acceptance acknowledgements."""

from __future__ import annotations
from dataclasses import dataclass, field
import struct
import zlib
from .wire import DecodedCsiPacket, decode_csi_packet

HEADER = struct.Struct("!4sBBHQIII6sHI")
ACK_HEADER = struct.Struct("!4sQIII6s")
MAX_ENVELOPE = 1400


def checked(data: bytes, magic: bytes, size: int | None = None) -> bytes:
    """Validate a complete versioned message CRC before using its fields."""
    if (
        len(data) < 8
        or data[:4] != magic
        or (size is not None and len(data) != size)
        or zlib.crc32(data[:-4]) != struct.unpack_from("!I", data, len(data) - 4)[0]
    ):
        raise ValueError("invalid gateway message length, magic or CRC")
    return data


@dataclass(frozen=True)
class GatewayBatch:
    """One atomic batch, qualified by run, boots, receiver identity and CRC."""

    run_id: int
    transmitter_boot_id: int
    receiver_boot_id: int
    batch_id: int
    receiver_mac: str
    payload: bytes
    _decoded_packet: DecodedCsiPacket | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _encoded: bytes | None = field(default=None, init=False, repr=False, compare=False)

    @property
    def decoded_packet(self) -> DecodedCsiPacket:
        """Return the validated immutable payload without repeating decoding."""
        if self._decoded_packet is None:
            packet = decode_csi_packet(self.payload)
            if (
                packet.boot_id != self.receiver_boot_id
                or packet.batch_sequence != self.batch_id
                or not packet.records
                or any(r.receiver_mac != self.receiver_mac for r in packet.records)
            ):
                raise ValueError("gateway and nested CSI identities disagree")
            object.__setattr__(self, "_decoded_packet", packet)
        return self._decoded_packet

    def encode(self) -> bytes:
        """Encode without fragmentation; maximum includes the entire envelope."""
        if self._encoded is not None:
            return self._encoded
        from ..espnow_config import mac_bytes

        p = (
            HEADER.pack(
                b"CGWY",
                1,
                0,
                HEADER.size,
                self.run_id,
                self.transmitter_boot_id,
                self.receiver_boot_id,
                self.batch_id,
                mac_bytes(self.receiver_mac),
                len(self.payload),
                0,
            )
            + self.payload
        )
        if not 0 < self.run_id < 1 << 64 or len(p) + 4 > MAX_ENVELOPE:
            raise ValueError("gateway envelope exceeds size/identity contract")
        return p + struct.pack("!I", zlib.crc32(p))

    @classmethod
    def decode(cls, data: bytes) -> GatewayBatch:
        """Validate envelope and every nested record's physical identity."""
        checked(data, b"CGWY")
        if not HEADER.size + 4 < len(data) <= MAX_ENVELOPE:
            raise ValueError("invalid envelope size")
        magic, version, flags, size, run, tx, rx, batch, mac, length, reserved = (
            HEADER.unpack_from(data)
        )
        if (version, flags, size, reserved) != (1, 0, HEADER.size, 0) or not run:
            raise ValueError("unsupported gateway envelope")
        if len(data) != size + length + 4:
            raise ValueError("invalid payload length")
        payload = data[size:-4]
        receiver = ":".join(f"{b:02x}" for b in mac)
        decoded = cls(run, tx, rx, batch, receiver, payload)
        _ = decoded.decoded_packet
        object.__setattr__(decoded, "_encoded", data)
        return decoded

    @property
    def identity(self) -> tuple:
        """Return the complete receiver-qualified duplicate identity."""
        return (
            self.run_id,
            self.transmitter_boot_id,
            self.receiver_mac,
            self.receiver_boot_id,
            self.batch_id,
        )

    def acknowledgement(self) -> bytes:
        """Acknowledge processor application acceptance, not just gateway receipt."""
        from ..espnow_config import mac_bytes

        p = ACK_HEADER.pack(
            b"CGAK",
            self.run_id,
            self.transmitter_boot_id,
            self.receiver_boot_id,
            self.batch_id,
            mac_bytes(self.receiver_mac),
        )
        return p + struct.pack("!I", zlib.crc32(p))
