import struct
from dataclasses import replace

import pytest

from fall_detection.radio.acquisition.protocol import format_csi_record
from fall_detection.radio.acquisition.protocol import parse_csi_line as _parse_csi_line
from fall_detection.radio.acquisition.wire import (
    BATCH_HEADER_SIZE,
    HEADER_SIZE,
    MAX_BATCH_RECORDS,
    MAX_DATAGRAM_SIZE,
    MAX_UDP_PAYLOAD,
    CsiDatagramError,
    DecodedCsiDatagram,
    ReceiverStats,
    encode_csi_batch,
    encode_csi_datagram,
)


def parse_csi_line(line):
    return replace(_parse_csi_line(line), profile_fingerprint="0123456789abcdef")


from wire_reference import decode_csi_datagram, decode_csi_packet

LINE = (
    "CSI_DATA,10,1a:00:00:00:00:00,-40,11,1,2,0,1,1,0,1,0,1,-95,3,11,0,"
    '1234,1,36,7,6,1,"[3,4,0,-5,127,-128]"'
)


STATS = ReceiverStats(
    accepted_records=100,
    sensing_missing=2,
    sensing_reordered=1,
    sensing_restarts=0,
    queue_drops=3,
    unavailable_ip_drops=4,
    batches_built=25,
    batches_sent=24,
    records_sent=96,
    send_errors=1,
)


def decoded_record(sequence: int, transport_sequence: int) -> DecodedCsiDatagram:
    record = parse_csi_line(LINE.replace("CSI_DATA,10,", f"CSI_DATA,{sequence},"))
    return DecodedCsiDatagram(
        record=record,
        receiver_mac="24:6f:28:aa:bb:cc",
        transport_sequence=transport_sequence,
    )


def test_binary_wire_round_trip_preserves_metadata_and_csv():
    record = parse_csi_line(LINE)
    packet = encode_csi_datagram(
        record,
        receiver_mac="24:6f:28:aa:bb:cc",
        transport_sequence=99,
    )

    decoded = decode_csi_datagram(packet)

    assert HEADER_SIZE == 87
    assert len(packet) <= MAX_DATAGRAM_SIZE
    assert decoded.receiver_mac == "24:6f:28:aa:bb:cc"
    assert decoded.transport_sequence == 99
    assert decoded.record.sequence == record.sequence
    assert decoded.record.mac == record.mac
    assert decoded.record.rssi == record.rssi
    assert decoded.record.noise_floor == record.noise_floor
    assert decoded.record.tx_timestamp_us is None
    assert decoded.record.rx_callback_timestamp_us is None
    assert decoded.record.raw_csi == record.raw_csi
    round_trip = parse_csi_line(format_csi_record(decoded.record))
    assert round_trip.sequence == decoded.record.sequence
    assert round_trip.mac == decoded.record.mac
    assert round_trip.raw_csi == decoded.record.raw_csi


def test_binary_wire_handles_maximum_csi_payload():
    values = [
        complex((index % 255) - 128, ((index * 3) % 255) - 128) for index in range(306)
    ]
    record = parse_csi_line(
        'CSI_DATA,2,1a:00:00:00:00:00,-40,11,1,0,0,1,1,0,0,0,0,-95,0,11,0,100,0,36,0,612,0,"'
        + str(
            [
                component
                for value in values
                for component in (int(value.imag), int(value.real))
            ]
        ).replace("'", "")
        + '"'
    )

    packet = encode_csi_datagram(
        record,
        receiver_mac="24:6f:28:aa:bb:cc",
        transport_sequence=0xFFFFFFFF,
    )

    assert len(packet) == MAX_DATAGRAM_SIZE
    assert decode_csi_datagram(packet).record.raw_csi == record.raw_csi


@pytest.mark.parametrize(
    "mutator",
    [
        lambda packet: b"BAD!" + packet[4:],
        lambda packet: packet[:4] + bytes([1]) + packet[5:],
        lambda packet: packet[:4] + bytes([2]) + packet[5:],
        lambda packet: packet[:4] + bytes([9]) + packet[5:],
        lambda packet: packet[:-1],
        lambda packet: packet[: HEADER_SIZE - 1] + packet[HEADER_SIZE:],
    ],
)
def test_binary_wire_rejects_corrupt_datagrams(mutator):
    packet = encode_csi_datagram(
        parse_csi_line(LINE),
        receiver_mac="24:6f:28:aa:bb:cc",
        transport_sequence=1,
    )

    with pytest.raises(CsiDatagramError):
        decode_csi_datagram(mutator(packet))


def test_binary_wire_uses_explicit_network_byte_order():
    packet = encode_csi_datagram(
        parse_csi_line(LINE),
        receiver_mac="24:6f:28:aa:bb:cc",
        transport_sequence=0x01020304,
    )

    assert packet[22:26] == struct.pack("!I", 0x01020304)


def test_packet_decoder_rejects_unbatched_records():
    encoded = encode_csi_datagram(
        parse_csi_line(LINE), receiver_mac="24:6f:28:aa:bb:cc", transport_sequence=7
    )
    with pytest.raises(CsiDatagramError):
        decode_csi_packet(encoded)


def test_batch_round_trip_preserves_four_records_and_stats():
    records = tuple(decoded_record(sequence, sequence + 40) for sequence in range(4))

    encoded = encode_csi_batch(
        records,
        boot_id=0x10203040,
        batch_sequence=9,
        receiver_stats=STATS,
    )
    packet = decode_csi_packet(encoded)

    assert BATCH_HEADER_SIZE == 60
    assert MAX_BATCH_RECORDS == 4
    assert len(encoded) <= MAX_UDP_PAYLOAD
    assert packet.boot_id == 0x10203040
    assert packet.batch_sequence == 9
    assert packet.receiver_stats == STATS
    assert [item.record.sequence for item in packet.records] == [0, 1, 2, 3]
    assert [item.transport_sequence for item in packet.records] == [40, 41, 42, 43]


def test_batch_accepts_two_large_clocked_records_below_payload_limit():
    values = [
        complex((index % 255) - 128, ((index * 3) % 255) - 128) for index in range(290)
    ]
    record = parse_csi_line(
        'CSI_DATA,2,1a:00:00:00:00:00,-40,11,1,0,0,1,1,0,0,0,0,-95,0,11,0,100,0,36,0,580,0,"'
        + str(
            [
                component
                for value in values
                for component in (int(value.imag), int(value.real))
            ]
        ).replace("'", "")
        + '"'
    )
    records = tuple(
        DecodedCsiDatagram(
            record=record,
            receiver_mac="24:6f:28:aa:bb:cc",
            transport_sequence=index,
        )
        for index in range(2)
    )

    encoded = encode_csi_batch(
        records,
        boot_id=1,
        batch_sequence=2,
        receiver_stats=STATS,
    )

    assert len(encoded) == 1398
    assert len(decode_csi_packet(encoded).records) == 2


def test_binary_wire_preserves_cross_clock_timestamps():
    record = replace(
        parse_csi_line(LINE),
        tx_timestamp_us=0x0102030405060708,
        rx_callback_timestamp_us=0x1112131415161718,
    )

    decoded = decode_csi_datagram(
        encode_csi_datagram(
            record,
            receiver_mac="24:6f:28:aa:bb:cc",
            transport_sequence=3,
        )
    )

    assert decoded.record.tx_timestamp_us == 0x0102030405060708
    assert decoded.record.rx_callback_timestamp_us == 0x1112131415161718


def test_batch_rejects_payload_over_1400_bytes():
    maximum = decode_csi_datagram(
        encode_csi_datagram(
            parse_csi_line(
                'CSI_DATA,2,1a:00:00:00:00:00,-40,11,1,0,0,1,1,0,0,0,0,-95,0,11,0,100,0,36,0,612,0,"'
                + str([0] * 612)
                + '"'
            ),
            receiver_mac="24:6f:28:aa:bb:cc",
            transport_sequence=1,
        )
    )

    with pytest.raises(CsiDatagramError, match="exceeds"):
        encode_csi_batch(
            (maximum, maximum, maximum),
            boot_id=1,
            batch_sequence=2,
            receiver_stats=STATS,
        )


@pytest.mark.parametrize(
    "mutator",
    [
        lambda packet: b"BAD!" + packet[4:],
        lambda packet: packet[:4] + bytes([9]) + packet[5:],
        lambda packet: packet[:16] + b"\x00\x05" + packet[18:],
        lambda packet: packet[:-1],
        lambda packet: packet + b"\x00",
    ],
)
def test_batch_rejects_corrupt_envelope(mutator):
    encoded = encode_csi_batch(
        (decoded_record(1, 1),),
        boot_id=1,
        batch_sequence=2,
        receiver_stats=STATS,
    )

    with pytest.raises(CsiDatagramError):
        decode_csi_packet(mutator(encoded))
