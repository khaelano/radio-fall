"""Independent current-format decoder used to check the Rust implementation."""

import re
import struct
from math import nan

from fall_detection.radio.acquisition.protocol import CsiRecord
from fall_detection.radio.acquisition.wire import (
    BATCH_HEADER,
    BATCH_HEADER_SIZE,
    BATCH_MAGIC,
    BATCH_VERSION,
    CLOCK_TIMESTAMPS_VALID,
    ENTRY_LENGTH,
    FIRST_WORD_INVALID,
    HEADER,
    HEADER_SIZE,
    MAGIC,
    MAX_BATCH_RECORDS,
    MAX_CSI_BYTES,
    MAX_UDP_PAYLOAD,
    VERSION,
    CsiDatagramError,
    DecodedCsiDatagram,
    DecodedCsiPacket,
    ReceiverStats,
)


def _mac_text(value: bytes) -> str:
    return ":".join(f"{octet:02x}" for octet in value)


def decode_csi_datagram(data: bytes) -> DecodedCsiDatagram:
    """Validate and decode one UDP datagram from an ESP32 receiver."""

    if len(data) < HEADER_SIZE:
        raise CsiDatagramError("datagram is shorter than the wire header")
    magic, version, flags, header_length = struct.unpack_from("!4sBBH", data)
    if magic != MAGIC or version != VERSION:
        raise CsiDatagramError("unsupported CSI wire magic or version")
    if header_length != HEADER_SIZE:
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
    ) = HEADER.unpack_from(data)

    allowed_flags = FIRST_WORD_INVALID | CLOCK_TIMESTAMPS_VALID
    fingerprint_bytes = clock_values[2]
    try:
        profile_fingerprint = fingerprint_bytes.decode("ascii")
    except UnicodeDecodeError as exc:
        raise CsiDatagramError("invalid profile fingerprint") from exc
    if re.fullmatch(r"[0-9a-fA-F]{16}", profile_fingerprint) is None:
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


def decode_csi_packet(data: bytes) -> DecodedCsiPacket:
    """Decode and validate a CSIB batch."""

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
        if record_length < HEADER_SIZE or offset + record_length > len(data):
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
