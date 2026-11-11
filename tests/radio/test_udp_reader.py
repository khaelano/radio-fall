import socket
import time
from pathlib import Path

from fall_detection.radio.acquisition.buffer import RollingCsiBuffer
from fall_detection.radio.acquisition.protocol import parse_csi_line
from fall_detection.radio.acquisition.udp_reader import UdpCsiReader
from fall_detection.radio.acquisition.wire import encode_csi_datagram
from fall_detection.radio.acquisition.wire import (
    DecodedCsiDatagram,
    ReceiverStats,
    encode_csi_batch,
)


LINE = (
    "CSI_DATA,10,1a:00:00:00:00:00,-40,11,1,0,0,1,1,0,0,0,0,-95,0,11,0,"
    '1000,0,36,0,4,0,"[3,4,0,5]"'
)


STATS = ReceiverStats(
    accepted_records=20,
    sensing_missing=2,
    sensing_reordered=0,
    sensing_restarts=0,
    queue_drops=0,
    unavailable_ip_drops=0,
    batches_built=5,
    batches_sent=5,
    records_sent=20,
    send_errors=0,
)


def _wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert predicate()


def test_udp_reader_ingests_records_and_preserves_csv(tmp_path: Path):
    reader = UdpCsiReader(
        "127.0.0.1",
        0,
        RollingCsiBuffer(nominal_rate=100, seconds=10),
        tmp_path,
    )
    reader.start()
    _wait_until(lambda: reader.bound_port is not None)

    packet = encode_csi_datagram(
        parse_csi_line(LINE),
        receiver_mac="24:6f:28:aa:bb:cc",
        transport_sequence=4,
    )
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        sender.sendto(packet, ("127.0.0.1", reader.bound_port))

    _wait_until(lambda: reader.buffer.received_records == 1)
    reader.stop()

    captures = list(tmp_path.glob("csi_*.csv"))
    assert len(captures) == 1
    assert (
        captures[0]
        .read_text(encoding="utf-8")
        .splitlines()[1]
        .startswith("CSI_DATA,10,1a:00:00:00:00:00")
    )
    assert reader.transport_missing == 0


def test_udp_reader_can_forward_records_to_an_active_collection_sink(tmp_path: Path):
    forwarded = []
    reader = UdpCsiReader(
        "127.0.0.1",
        0,
        RollingCsiBuffer(nominal_rate=100, seconds=10),
        tmp_path,
        record_sink=lambda record, timestamp: forwarded.append((record, timestamp)),
    )
    reader.start()
    _wait_until(lambda: reader.bound_port is not None)

    packet = encode_csi_datagram(
        parse_csi_line(LINE),
        receiver_mac="24:6f:28:aa:bb:cc",
        transport_sequence=4,
    )
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        sender.sendto(packet, ("127.0.0.1", reader.bound_port))

    _wait_until(lambda: len(forwarded) == 1)
    reader.stop()

    assert forwarded[0][0].sequence == 10
    assert forwarded[0][1] > 0
    assert not list(tmp_path.glob("csi_*.csv"))


def test_udp_reader_tracks_transport_gaps_and_filters_foreign_receiver(tmp_path: Path):
    reader = UdpCsiReader(
        "127.0.0.1",
        0,
        RollingCsiBuffer(nominal_rate=100, seconds=10),
        tmp_path,
        receiver_mac="24:6f:28:aa:bb:cc",
    )
    reader.start()
    _wait_until(lambda: reader.bound_port is not None)

    record = parse_csi_line(LINE)
    packets = [
        encode_csi_datagram(
            record, receiver_mac="24:6f:28:aa:bb:cc", transport_sequence=10
        ),
        encode_csi_datagram(
            record, receiver_mac="24:6f:28:aa:bb:cc", transport_sequence=12
        ),
        encode_csi_datagram(
            record, receiver_mac="24:6f:28:aa:bb:dd", transport_sequence=11
        ),
    ]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        for packet in packets:
            sender.sendto(packet, ("127.0.0.1", reader.bound_port))

    _wait_until(lambda: reader.buffer.received_records == 2)
    reader.stop()

    assert reader.transport_missing == 1
    assert reader.foreign_datagrams == 1


def test_udp_reader_ingests_batches_and_tracks_batch_gaps(tmp_path: Path):
    reader = UdpCsiReader(
        "127.0.0.1",
        0,
        RollingCsiBuffer(nominal_rate=100, seconds=10),
        tmp_path,
    )
    reader.start()
    _wait_until(lambda: reader.bound_port is not None)

    source = parse_csi_line(LINE)
    first = DecodedCsiDatagram(source, "24:6f:28:aa:bb:cc", 10)
    second = DecodedCsiDatagram(source, "24:6f:28:aa:bb:cc", 11)
    packets = [
        encode_csi_batch((first,), boot_id=55, batch_sequence=3, receiver_stats=STATS),
        encode_csi_batch((second,), boot_id=55, batch_sequence=5, receiver_stats=STATS),
    ]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        for packet in packets:
            sender.sendto(packet, ("127.0.0.1", reader.bound_port))

    _wait_until(lambda: reader.buffer.received_records == 2)
    reader.stop()

    assert reader.batch_missing == 1
    assert reader.transport_missing == 0
    assert reader.receiver_boot_id == 55
    assert reader.receiver_stats == STATS


def test_udp_reader_resets_sequence_epochs_when_boot_id_changes(tmp_path: Path):
    reader = UdpCsiReader(
        "127.0.0.1",
        0,
        RollingCsiBuffer(nominal_rate=100, seconds=10),
        tmp_path,
    )
    reader.start()
    _wait_until(lambda: reader.bound_port is not None)

    source = parse_csi_line(LINE)
    packets = [
        encode_csi_batch(
            (DecodedCsiDatagram(source, "24:6f:28:aa:bb:cc", 100),),
            boot_id=1,
            batch_sequence=100,
            receiver_stats=STATS,
        ),
        encode_csi_batch(
            (DecodedCsiDatagram(source, "24:6f:28:aa:bb:cc", 0),),
            boot_id=2,
            batch_sequence=0,
            receiver_stats=STATS,
        ),
    ]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        for packet in packets:
            sender.sendto(packet, ("127.0.0.1", reader.bound_port))

    _wait_until(lambda: reader.buffer.received_records == 2)
    reader.stop()

    assert reader.receiver_restarts == 1
    assert reader.transport_missing == 0
    assert reader.batch_missing == 0


def test_udp_reader_does_not_move_transport_high_water_mark_on_reorder(tmp_path: Path):
    reader = UdpCsiReader(
        "127.0.0.1",
        0,
        RollingCsiBuffer(nominal_rate=100, seconds=10),
        tmp_path,
    )
    reader.start()
    _wait_until(lambda: reader.bound_port is not None)

    source = parse_csi_line(LINE)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        for sequence in (10, 9, 11):
            sender.sendto(
                encode_csi_datagram(
                    source,
                    receiver_mac="24:6f:28:aa:bb:cc",
                    transport_sequence=sequence,
                ),
                ("127.0.0.1", reader.bound_port),
            )

    _wait_until(lambda: reader.buffer.received_records == 3)
    reader.stop()

    assert reader.transport_reordered == 1
    assert reader.transport_missing == 0


def test_udp_reader_tracks_transport_and_batch_sequence_wrap(tmp_path: Path):
    reader = UdpCsiReader(
        "127.0.0.1",
        0,
        RollingCsiBuffer(nominal_rate=100, seconds=10),
        tmp_path,
    )

    reader._track_transport_sequence(0xFFFFFFFF)
    reader._track_transport_sequence(0)
    reader._track_batch_sequence(0xFFFFFFFF)
    reader._track_batch_sequence(0)

    assert reader.transport_missing == 0
    assert reader.transport_reordered == 0
    assert reader.batch_missing == 0
    assert reader.batch_reordered == 0
