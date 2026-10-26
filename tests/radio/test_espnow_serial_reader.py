from pathlib import Path

from fall_detection.radio.acquisition.buffer import RollingCsiBuffer
from fall_detection.radio.acquisition.clock_sync import MAGIC, SAMPLE, SAMPLE_SIZE, VERSION
from fall_detection.radio.acquisition.espnow_serial_reader import EspNowSerialCsiReader
from fall_detection.radio.acquisition.protocol import parse_csi_line
from fall_detection.radio.acquisition.serial_framing import (
    TYPE_CSI_PACKET,
    TYPE_CLOCK_SYNC,
    TYPE_GATEWAY_STATS,
    TYPE_TRANSMITTER_STATS,
    SerialFrame,
)
from fall_detection.radio.acquisition.wire import (
    DecodedCsiDatagram,
    ReceiverStats,
    encode_csi_batch,
)


LINE = (
    'CSI_DATA,10,1a:00:00:00:00:00,-40,11,1,0,0,1,1,0,0,0,0,-95,0,11,0,'
    '1000,0,36,0,4,0,"[3,4,0,5]"'
)


def _batch() -> bytes:
    record = parse_csi_line(LINE)
    return encode_csi_batch(
        (DecodedCsiDatagram(record, "24:6f:28:aa:bb:cc", 4),),
        boot_id=7,
        batch_sequence=2,
        receiver_stats=ReceiverStats(10, 0, 0, 0, 0, 0, 2, 2, 10, 0),
    )


def test_espnow_serial_reader_ingests_csi_and_gateway_telemetry(tmp_path: Path):
    reader = EspNowSerialCsiReader(
        "/dev/null",
        921600,
        RollingCsiBuffer(nominal_rate=100, seconds=10),
        tmp_path,
    )

    reader._handle_frame(SerialFrame(TYPE_CSI_PACKET, _batch()))
    reader._handle_frame(
        SerialFrame(TYPE_TRANSMITTER_STATS, b"CSI_TX_STATS,1000,100,0,99,1")
    )
    reader._handle_frame(
        SerialFrame(TYPE_GATEWAY_STATS, b"CSI_GATEWAY_STATS,1000,25,1,2,22,3")
    )
    reader._handle_frame(
        SerialFrame(
            TYPE_CLOCK_SYNC,
            SAMPLE.pack(
                MAGIC,
                VERSION,
                0,
                SAMPLE_SIZE,
                3,
                10,
                7,
                0,
                1_000,
                6_300,
                6_700,
                2_000,
                100,
                200,
                bytes.fromhex("246f28aabbcc"),
                0,
            ),
        )
    )
    reader._close_packet_stream()

    assert reader.buffer.received_records == 1
    assert reader.receiver_boot_id == 7
    assert reader.transmitter_stats is not None
    assert reader.transmitter_stats.attempts == 100
    assert reader.gateway_stats is not None
    assert reader.gateway_stats.queue_drops == 2
    assert reader.clock_sync_frames == 1
    assert reader.clock_sync.estimate is not None
    assert reader.clock_sync.estimate.receiver_minus_transmitter_us == 5_000
    assert reader.serial_frames == 4


def test_espnow_serial_reader_rejects_foreign_receiver(tmp_path: Path):
    reader = EspNowSerialCsiReader(
        "/dev/null",
        921600,
        RollingCsiBuffer(nominal_rate=100, seconds=10),
        tmp_path,
        receiver_mac="24:6f:28:aa:bb:dd",
    )

    reader._handle_frame(SerialFrame(TYPE_CSI_PACKET, _batch()))

    assert reader.buffer.received_records == 0
    assert reader.foreign_packets == 1
