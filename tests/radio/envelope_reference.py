"""Independent CGWY envelope encoder used to build firmware and Rust fixtures."""

import struct
import zlib
from dataclasses import dataclass

from fall_detection.radio.espnow_config import mac_bytes

HEADER = struct.Struct("!4sBBHQIII6sHI")
ACK_HEADER = struct.Struct("!4sQIII6s")
MAX_ENVELOPE = 1400


@dataclass(frozen=True)
class Envelope:
    """One atomic batch, qualified by run, boots, receiver identity and CRC."""

    run_id: int
    transmitter_boot_id: int
    receiver_boot_id: int
    batch_id: int
    receiver_mac: str
    payload: bytes

    def encode(self) -> bytes:
        """Encode without fragmentation; the maximum includes the entire envelope."""
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

    def acknowledgement(self) -> bytes:
        """Acknowledge application acceptance of this batch."""
        p = ACK_HEADER.pack(
            b"CGAK",
            self.run_id,
            self.transmitter_boot_id,
            self.receiver_boot_id,
            self.batch_id,
            mac_bytes(self.receiver_mac),
        )
        return p + struct.pack("!I", zlib.crc32(p))
