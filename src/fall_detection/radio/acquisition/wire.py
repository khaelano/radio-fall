"""Binary CSI wire format used by the Espressif USB receiver."""

from __future__ import annotations

import struct
from dataclasses import astuple, dataclass
from math import nan
import re

from .protocol import CsiRecord, format_csi_record


MAGIC = b"CSI1"
LEGACY_VERSION = 1
VERSION = 2
PROFILE_VERSION = 3
BATCH_MAGIC = b"CSIB"
BATCH_VERSION = 1
MAX_CSI_BYTES = 612
FIRST_WORD_INVALID = 1 << 0
CLOCK_TIMESTAMPS_VALID = 1 << 1
LEGACY_HEADER = struct.Struct("!4sBBHH6s6sIIIbb15BHH")
HEADER = struct.Struct("!4sBBHH6s6sIIIbb15BHHQQ")
PROFILE_HEADER = struct.Struct("!4sBBHH6s6sIIIbb15BHHQQ16s")
LEGACY_HEADER_SIZE = LEGACY_HEADER.size
HEADER_SIZE = HEADER.size
PROFILE_HEADER_SIZE = PROFILE_HEADER.size
MAX_DATAGRAM_SIZE = HEADER_SIZE + MAX_CSI_BYTES
MAX_PROFILE_DATAGRAM_SIZE = PROFILE_HEADER_SIZE + MAX_CSI_BYTES
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


def _mac_text(value: bytes) -> str:
    return ":".join(f"{octet:02x}" for octet in value)


def encode_csi_datagram(
    record: CsiRecord,
    *,
    receiver_mac: str,
    transport_sequence: int,
) -> bytes:
    """Encode one record using the ESP32 receiver's network byte order.

    Fingerprinted records use CSI1 v3. Empty fingerprints retain v2 decoding
    compatibility for existing raw recordings.
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
    if fingerprint:
        if (
            len(fingerprint) != 16
            or re.fullmatch(r"[0-9a-fA-F]{16}", fingerprint) is None
        ):
            raise CsiDatagramError(
                "profile fingerprint must be 16 hexadecimal characters"
            )
        header = PROFILE_HEADER.pack(
            MAGIC,
            PROFILE_VERSION,
            flags,
            PROFILE_HEADER_SIZE,
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
    else:
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
        )
    return header + payload


def decode_csi_datagram(data: bytes) -> DecodedCsiDatagram:
    """Validate and decode one UDP datagram from an ESP32 receiver."""

    if len(data) < LEGACY_HEADER_SIZE:
        raise CsiDatagramError("datagram is shorter than the wire header")
    magic, version, flags, header_length = struct.unpack_from("!4sBBH", data)
    if magic != MAGIC or version not in (LEGACY_VERSION, VERSION, PROFILE_VERSION):
        raise CsiDatagramError("unsupported CSI wire magic or version")
    expected_header = (
        LEGACY_HEADER
        if version == LEGACY_VERSION
        else PROFILE_HEADER
        if version == PROFILE_VERSION
        else HEADER
    )
    if header_length != expected_header.size or len(data) < header_length:
        raise CsiDatagramError("unexpected CSI wire header length")
    (
        _,
        _,
        _,
        _,
        payload_length,
        receiver_bytes,
        transmitter_bytes,
        transport_sequence,
        sensing_sequence,
        timestamp,
        rssi,
        noise_floor,
        rate,
        sig_mode,
        mcs,
        bandwidth,
        smoothing,
        not_sounding,
        aggregation,
        stbc,
        fec_coding,
        sgi,
        ampdu_count,
        channel,
        secondary_channel,
        antenna,
        rx_state,
        sig_len,
        csi_length,
        *clock_values,
    ) = expected_header.unpack_from(data)

    allowed_flags = FIRST_WORD_INVALID
    profile_fingerprint = ""
    if version in (VERSION, PROFILE_VERSION):
        allowed_flags |= CLOCK_TIMESTAMPS_VALID
    if version == PROFILE_VERSION:
        fingerprint_bytes = clock_values[2]
        profile_fingerprint = fingerprint_bytes.split(b"\0", 1)[0].decode(
            "ascii", errors="strict"
        )
        if (
            len(profile_fingerprint) != 16
            or re.fullmatch(r"[0-9a-fA-F]{16}", profile_fingerprint) is None
        ):
            raise CsiDatagramError("invalid profile fingerprint")
        clock_values = clock_values[:2]
    if flags & ~allowed_flags:
        raise CsiDatagramError("unknown CSI wire flags")
    clocks_valid = bool(flags & CLOCK_TIMESTAMPS_VALID)
    if clocks_valid:
        tx_timestamp_us, rx_callback_timestamp_us = clock_values
    else:
        tx_timestamp_us = None
        rx_callback_timestamp_us = None
    if payload_length != csi_length or csi_length == 0 or csi_length % 2:
        raise CsiDatagramError("invalid CSI payload length")
    if csi_length > MAX_CSI_BYTES or len(data) != header_length + csi_length:
        raise CsiDatagramError("CSI datagram length does not match its header")

    receiver_mac = _mac_text(receiver_bytes)
    transmitter_mac = _mac_text(transmitter_bytes)
    raw_values = data[header_length:]
    raw_csi = tuple(
        complex(
            raw_values[index + 1] - 256
            if raw_values[index + 1] > 127
            else raw_values[index + 1],
            raw_values[index] - 256 if raw_values[index] > 127 else raw_values[index],
        )
        for index in range(0, len(raw_values), 2)
    )
    csi = list(raw_csi)
    first_word_invalid = bool(flags & FIRST_WORD_INVALID)
    if first_word_invalid:
        for index in range(min(2, len(csi))):
            csi[index] = complex(nan, nan)

    record = CsiRecord(
        sequence=sensing_sequence,
        mac=transmitter_mac,
        rssi=rssi,
        noise_floor=noise_floor,
        timestamp_us=timestamp,
        csi=tuple(csi),
        raw_line="",
        receiver_mac=receiver_mac,
        transport_sequence=transport_sequence,
        tx_timestamp_us=tx_timestamp_us,
        rx_callback_timestamp_us=rx_callback_timestamp_us,
        first_word_invalid=first_word_invalid,
        rate=rate,
        sig_mode=sig_mode,
        mcs=mcs,
        bandwidth=bandwidth,
        smoothing=smoothing,
        not_sounding=not_sounding,
        aggregation=aggregation,
        secondary_channel=secondary_channel,
        stbc=stbc,
        fec_coding=fec_coding,
        sgi=sgi,
        ampdu_count=ampdu_count,
        channel=channel,
        antenna=antenna,
        sig_len=sig_len,
        rx_state=rx_state,
        csi_length=csi_length,
        raw_csi=raw_csi,
        profile_fingerprint=profile_fingerprint,
    )
    return DecodedCsiDatagram(
        record=record,
        receiver_mac=receiver_mac,
        transport_sequence=transport_sequence,
    )


def encode_csi_batch(
    records: tuple[DecodedCsiDatagram, ...],
    *,
    boot_id: int,
    batch_sequence: int,
    receiver_stats: ReceiverStats,
) -> bytes:
    """Wrap one to four legacy ``CSI1`` records in a ``CSIB`` packet."""

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


def decode_csi_packet(data: bytes) -> DecodedCsiPacket:
    """Decode either one legacy record or a backward-compatible batch."""

    if data.startswith(MAGIC):
        return DecodedCsiPacket(records=(decode_csi_datagram(data),))
    if len(data) < BATCH_HEADER_SIZE:
        raise CsiDatagramError("packet is shorter than the batch header")

    unpacked = BATCH_HEADER.unpack_from(data)
    (
        magic,
        version,
        flags,
        header_length,
        boot_id,
        batch_sequence,
        record_count,
        reserved,
        *counter_values,
    ) = unpacked
    if magic != BATCH_MAGIC or version != BATCH_VERSION:
        raise CsiDatagramError("unsupported CSI packet magic or version")
    if flags != 0 or reserved != 0:
        raise CsiDatagramError("unknown batch flags or reserved value")
    if header_length != BATCH_HEADER_SIZE:
        raise CsiDatagramError("unexpected batch header length")
    if not 1 <= record_count <= MAX_BATCH_RECORDS:
        raise CsiDatagramError("invalid batch record count")
    if len(data) > MAX_UDP_PAYLOAD:
        raise CsiDatagramError("batch exceeds the UDP payload limit")

    records: list[DecodedCsiDatagram] = []
    offset = header_length
    receiver_mac: str | None = None
    for _ in range(record_count):
        if offset + ENTRY_LENGTH.size > len(data):
            raise CsiDatagramError("batch is missing a record length")
        (record_length,) = ENTRY_LENGTH.unpack_from(data, offset)
        offset += ENTRY_LENGTH.size
        if record_length < LEGACY_HEADER_SIZE or offset + record_length > len(data):
            raise CsiDatagramError("batch record length is invalid")
        decoded = decode_csi_datagram(data[offset : offset + record_length])
        offset += record_length
        if receiver_mac is None:
            receiver_mac = decoded.receiver_mac
        elif decoded.receiver_mac != receiver_mac:
            raise CsiDatagramError("batch contains multiple receiver MACs")
        records.append(decoded)
    if offset != len(data):
        raise CsiDatagramError("batch has trailing bytes")

    return DecodedCsiPacket(
        records=tuple(records),
        boot_id=boot_id,
        batch_sequence=batch_sequence,
        receiver_stats=ReceiverStats(*counter_values),
    )


def decoded_csv_line(decoded: DecodedCsiDatagram) -> str:
    """Return the legacy CSV representation for a decoded datagram."""

    return format_csi_record(decoded.record)
