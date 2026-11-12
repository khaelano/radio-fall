"""Binary CSI wire format used by the Espressif USB receiver."""

from __future__ import annotations

import re
import struct
from dataclasses import astuple, dataclass

from .protocol import CsiRecord

MAGIC = b"CSI1"
VERSION = 3
BATCH_MAGIC = b"CSIB"
BATCH_VERSION = 1
MAX_CSI_BYTES = 612
FIRST_WORD_INVALID = 1 << 0
CLOCK_TIMESTAMPS_VALID = 1 << 1
HEADER = struct.Struct("!4sBBHH6s6sIIIbb15BHHQQ16s")
HEADER_SIZE = HEADER.size
MAX_DATAGRAM_SIZE = HEADER_SIZE + MAX_CSI_BYTES
MAX_UDP_PAYLOAD = 1400
MAX_BATCH_RECORDS = 4
# magic, version, flags, header length, boot id, batch sequence, record count,
# reserved, followed by the ten cumulative ReceiverStats counters.
BATCH_HEADER = struct.Struct("!4sBBHIIHH10I")
BATCH_HEADER_SIZE = BATCH_HEADER.size
ENTRY_LENGTH = struct.Struct("!H")
MAC_PATTERN = re.compile(r"[0-9a-f]{2}(?::[0-9a-f]{2}){5}\Z")


class CsiDatagramError(ValueError):
    """Raised when a datagram fails the CSI wire-format checks."""


@dataclass(frozen=True)
class DecodedCsiDatagram:
    """Decoded measurement plus transport metadata."""

    record: CsiRecord
    receiver_mac: str
    transport_sequence: int


@dataclass(frozen=True)
class ReceiverStats:
    """Cumulative receiver counters carried by a batched packet."""

    accepted_records: int
    sensing_missing: int
    sensing_reordered: int
    sensing_restarts: int
    queue_drops: int
    unavailable_ip_drops: int
    batches_built: int
    batches_sent: int
    records_sent: int
    send_errors: int


@dataclass(frozen=True)
class DecodedCsiPacket:
    """One UDP packet containing one or more CSI records."""

    records: tuple[DecodedCsiDatagram, ...]
    boot_id: int | None = None
    batch_sequence: int | None = None
    receiver_stats: ReceiverStats | None = None


def _mac_bytes(mac: str, field: str) -> bytes:
    normalized = mac.lower()
    if MAC_PATTERN.fullmatch(normalized) is None:
        raise ValueError(f"invalid {field} MAC")
    return bytes.fromhex(normalized.replace(":", ""))


def encode_csi_datagram(
    record: CsiRecord,
    *,
    receiver_mac: str,
    transport_sequence: int,
) -> bytes:
    """Encode one record using the ESP32 receiver's network byte order.

    Records require the configured CSI1 v3 profile fingerprint.
    """

    raw_csi = record.raw_csi or record.csi
    csi_values: list[int] = []
    for value in raw_csi:
        csi_values.extend((int(value.imag), int(value.real)))
    payload = bytes(value & 0xFF for value in csi_values)
    if not payload or len(payload) > MAX_CSI_BYTES or len(payload) % 2:
        raise CsiDatagramError(
            "CSI payload must be non-empty, even, and at most 612 bytes"
        )
    if not 0 <= transport_sequence <= 0xFFFFFFFF:
        raise CsiDatagramError("transport sequence is outside uint32 range")

    flags = FIRST_WORD_INVALID if record.first_word_invalid else 0
    clocks_valid = (
        record.tx_timestamp_us is not None
        and record.rx_callback_timestamp_us is not None
    )
    if clocks_valid:
        if not 0 <= record.tx_timestamp_us <= 0xFFFFFFFFFFFFFFFF:
            raise CsiDatagramError("transmitter timestamp is outside uint64 range")
        if not 0 <= record.rx_callback_timestamp_us <= 0xFFFFFFFFFFFFFFFF:
            raise CsiDatagramError(
                "receiver callback timestamp is outside uint64 range"
            )
        flags |= CLOCK_TIMESTAMPS_VALID
    fingerprint = record.profile_fingerprint
    if len(fingerprint) != 16 or re.fullmatch(r"[0-9a-fA-F]{16}", fingerprint) is None:
        raise CsiDatagramError("profile fingerprint must be 16 hexadecimal characters")
    header = HEADER.pack(
        MAGIC,
        VERSION,
        flags,
        HEADER_SIZE,
        len(payload),
        _mac_bytes(receiver_mac, "receiver"),
        _mac_bytes(record.mac, "transmitter"),
        transport_sequence,
        record.sequence & 0xFFFFFFFF,
        record.timestamp_us & 0xFFFFFFFF,
        record.rssi,
        record.noise_floor,
        record.rate,
        record.sig_mode,
        record.mcs,
        record.bandwidth,
        record.smoothing,
        record.not_sounding,
        record.aggregation,
        record.stbc,
        record.fec_coding,
        record.sgi,
        record.ampdu_count,
        record.channel,
        record.secondary_channel,
        record.antenna,
        record.rx_state,
        record.sig_len,
        len(payload),
        record.tx_timestamp_us if clocks_valid else 0,
        record.rx_callback_timestamp_us if clocks_valid else 0,
        fingerprint.encode("ascii"),
    )
    return header + payload


def encode_csi_batch(
    records: tuple[DecodedCsiDatagram, ...],
    *,
    boot_id: int,
    batch_sequence: int,
    receiver_stats: ReceiverStats,
) -> bytes:
    """Wrap one to four CSI1 records in a CSIB batch."""

    if not 1 <= len(records) <= MAX_BATCH_RECORDS:
        raise CsiDatagramError("batch must contain one to four CSI records")
    if not 0 <= boot_id <= 0xFFFFFFFF:
        raise CsiDatagramError("boot id is outside uint32 range")
    if not 0 <= batch_sequence <= 0xFFFFFFFF:
        raise CsiDatagramError("batch sequence is outside uint32 range")

    encoded_records: list[bytes] = []
    receiver_mac: str | None = None
    for decoded in records:
        if receiver_mac is None:
            receiver_mac = decoded.receiver_mac
        elif decoded.receiver_mac != receiver_mac:
            raise CsiDatagramError("all records in a batch must have one receiver MAC")
        encoded_records.append(
            encode_csi_datagram(
                decoded.record,
                receiver_mac=decoded.receiver_mac,
                transport_sequence=decoded.transport_sequence,
            )
        )

    counters = astuple(receiver_stats)
    if any(not 0 <= value <= 0xFFFFFFFF for value in counters):
        raise CsiDatagramError("receiver counter is outside uint32 range")
    header = BATCH_HEADER.pack(
        BATCH_MAGIC,
        BATCH_VERSION,
        0,
        BATCH_HEADER_SIZE,
        boot_id,
        batch_sequence,
        len(encoded_records),
        0,
        *counters,
    )
    packet = bytearray(header)
    for encoded in encoded_records:
        packet.extend(ENTRY_LENGTH.pack(len(encoded)))
        packet.extend(encoded)
    if len(packet) > MAX_UDP_PAYLOAD:
        raise CsiDatagramError(
            f"batch exceeds the {MAX_UDP_PAYLOAD}-byte UDP payload limit"
        )
    return bytes(packet)
