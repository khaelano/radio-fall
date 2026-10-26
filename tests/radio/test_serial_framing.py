from pathlib import Path
import shutil
import subprocess

import pytest

from fall_detection.radio.acquisition.serial_framing import (
    MAX_PAYLOAD,
    TYPE_CSI_PACKET,
    TYPE_CLOCK_SYNC,
    TYPE_GATEWAY_STATS,
    SerialFrameError,
    SerialFrameStreamDecoder,
    cobs_decode,
    cobs_encode,
    decode_serial_frame,
    encode_serial_frame,
)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"plain text",
        b"\x00\x01\x00\xff",
        bytes(range(256)) * 5,
        bytes(index % 251 for index in range(MAX_PAYLOAD)),
    ],
)
def test_cobs_round_trip(payload: bytes):
    encoded = cobs_encode(payload)

    assert b"\x00" not in encoded
    assert cobs_decode(encoded) == payload


def test_serial_frame_round_trip_preserves_type_and_maximum_payload():
    payload = bytes(index % 256 for index in range(MAX_PAYLOAD))
    framed = encode_serial_frame(TYPE_CSI_PACKET, payload)

    assert framed[0] == 0
    assert framed[-1] == 0
    assert decode_serial_frame(framed[1:-1]).payload == payload


def test_serial_frame_accepts_clock_sync_type():
    framed = encode_serial_frame(TYPE_CLOCK_SYNC, b"clock sample")

    assert decode_serial_frame(framed[1:-1]).type == TYPE_CLOCK_SYNC


def test_serial_frame_rejects_crc_corruption():
    framed = bytearray(encode_serial_frame(TYPE_CSI_PACKET, b"CSIB payload"))
    framed[-3] ^= 0x01

    with pytest.raises(SerialFrameError):
        decode_serial_frame(bytes(framed[1:-1]))


def test_stream_decoder_ignores_boot_text_and_handles_incremental_frames():
    first = encode_serial_frame(TYPE_CSI_PACKET, b"first")
    second = encode_serial_frame(TYPE_GATEWAY_STATS, b"second")
    stream = b"boot log without delimiter" + first + second
    decoder = SerialFrameStreamDecoder()
    frames = []

    for index in range(0, len(stream), 7):
        frames.extend(decoder.feed(stream[index : index + 7]))

    assert [(frame.type, frame.payload) for frame in frames] == [
        (TYPE_CSI_PACKET, b"first"),
        (TYPE_GATEWAY_STATS, b"second"),
    ]
    assert decoder.malformed_frames == 0


def test_stream_decoder_resynchronizes_after_corrupt_frame():
    corrupt = bytearray(encode_serial_frame(TYPE_CSI_PACKET, b"bad"))
    corrupt[3] ^= 0x10
    valid = encode_serial_frame(TYPE_CSI_PACKET, b"good")
    decoder = SerialFrameStreamDecoder()

    frames = decoder.feed(bytes(corrupt) + valid)

    assert [frame.payload for frame in frames] == [b"good"]
    assert decoder.malformed_frames == 1


def test_firmware_encoder_matches_python_decoder(tmp_path: Path):
    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("a host C compiler is required for the firmware framing test")
    repository = Path(__file__).resolve().parents[2]
    include_dir = repository / "src/firmware/radio/transmitter/main"
    executable = tmp_path / "serial_frame_test"
    source = r"""
        #include <stdint.h>
        #include <stdio.h>
        #include "serial_frame.h"

        int main(void) {
            uint8_t payload[CSI_SERIAL_MAX_PAYLOAD];
            uint8_t raw[CSI_SERIAL_MAX_RAW_SIZE];
            uint8_t frame[CSI_SERIAL_MAX_FRAME_SIZE];
            for (size_t index = 0; index < sizeof(payload); ++index) {
                payload[index] = (uint8_t)(index % 251);
            }
            const size_t length = csi_serial_encode_frame(
                CSI_SERIAL_TYPE_PACKET, payload, sizeof(payload), raw,
                sizeof(raw), frame, sizeof(frame));
            if (length == 0 || fwrite(frame, 1, length, stdout) != length) {
                return 1;
            }
            return 0;
        }
    """
    subprocess.run(
        [
            compiler,
            "-std=c11",
            "-Wall",
            "-Werror",
            "-I",
            str(include_dir),
            "-x",
            "c",
            "-",
            "-o",
            str(executable),
        ],
        input=source,
        text=True,
        check=True,
    )

    framed = subprocess.check_output([str(executable)])

    assert framed[0] == 0 and framed[-1] == 0
    decoded = decode_serial_frame(framed[1:-1])
    assert decoded.type == TYPE_CSI_PACKET
    assert decoded.payload == bytes(index % 251 for index in range(MAX_PAYLOAD))
