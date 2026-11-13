"""Cross-check native hot paths against preserved Python wire/scientific contracts."""

import random
import struct
import zlib
from dataclasses import replace

import numpy as np
import pytest
from test_gateway import batch

from fall_detection import _radio_native as core
from fall_detection.radio.acquisition.native import NativeRecord
from fall_detection.radio.acquisition.protocol import format_csi_record
from fall_detection.radio.acquisition.serial_framing import (
    decode_serial_frame,
    encode_serial_frame,
)
from fall_detection.radio.acquisition.wire import (
    DecodedCsiDatagram,
    ReceiverStats,
    encode_csi_batch,
)


def packet(size, invalid=False, seed=17):
    base = batch()
    from wire_reference import decode_csi_packet

    record = decode_csi_packet(base.payload).records[0].record
    rng = random.Random(seed)
    values = tuple(
        complex(rng.randrange(-128, 128), rng.randrange(-128, 128)) for _ in range(size)
    )
    masked = tuple(
        complex(float("nan"), float("nan")) if invalid and i < 2 else v
        for i, v in enumerate(values)
    )
    record = replace(
        record,
        csi=masked,
        raw_csi=values,
        csi_length=2 * size,
        first_word_invalid=invalid,
    )
    payload = encode_csi_batch(
        (DecodedCsiDatagram(record, record.receiver_mac, record.transport_sequence),),
        boot_id=21,
        batch_sequence=1,
        receiver_stats=ReceiverStats(*([0] * 10)),
    )
    return replace(base, payload=payload)


@pytest.mark.parametrize("size", [245, 256])
@pytest.mark.parametrize("invalid", [False, True])
def test_native_matches_python_raw_csv_metadata_and_calibrated_phase(size, invalid):
    original = packet(size, invalid)
    from wire_reference import decode_csi_packet

    old = decode_csi_packet(original.payload).records[0].record
    decoded = core.decode_envelope(original.encode())
    new = NativeRecord(decoded.records[0])
    for key in [
        "sequence",
        "transport_sequence",
        "timestamp_us",
        "receiver_mac",
        "mac",
        "rssi",
        "noise_floor",
        "sig_len",
        "tx_timestamp_us",
        "rx_callback_timestamp_us",
        "csi_length",
        "first_word_invalid",
        "profile_fingerprint",
        "rate",
        "sig_mode",
        "mcs",
        "bandwidth",
        "stbc",
        "rx_state",
        "channel",
    ]:
        assert getattr(old, key) == getattr(new, key), key
    assert old.raw_csi == new.raw_csi
    np.testing.assert_allclose(old.csi, new.csi, equal_nan=True, atol=0)
    assert format_csi_record(old) == format_csi_record(new)
    assert old.mean_i == new.mean_i and old.mean_q == new.mean_q
    a, b = old.channel_estimate_block, new.channel_estimate_block
    assert a.subcarrier_indices == b.subcarrier_indices
    np.testing.assert_allclose(a.amplitudes, b.amplitudes, rtol=1e-14, atol=1e-13)
    np.testing.assert_allclose(a.raw_phases, b.raw_phases, equal_nan=True, atol=1e-14)
    error = np.angle(np.exp(1j * (np.array(a.calibrated_phases) - b.calibrated_phases)))
    assert np.nanmax(np.abs(error)) < 1e-10
    assert np.array_equal(np.isnan(a.calibrated_phases), np.isnan(b.calibrated_phases))
    assert not b.amplitudes.flags.writeable


def test_native_rejects_crc_and_preserves_record_context():
    original = batch().encode()
    bad = bytearray(original)
    bad[-5] ^= 1
    with pytest.raises(ValueError, match="CRC"):
        core.decode_envelope(bytes(bad))
    decoded = core.decode_envelope(original)
    assert bytes(decoded.payload) == batch().payload
    r = NativeRecord(decoded.records[0])
    updated = r.with_context({"run_id": 123, "capture_host_monotonic_ns": 999})
    assert r.run_id is None and updated.run_id == 123
    assert updated.capture_host_monotonic_ns == 999
    assert updated._native is r._native
    assert updated.channel_estimate_block is not None


def test_native_wire_rejects_truncations_and_malformed_nested_headers():
    original = batch().encode()
    for end in range(len(original)):
        with pytest.raises(ValueError):
            core.decode_envelope(original[:end])
    # Alter identity, reserved fields, lengths, nested header and record fields;
    # repair the outer CRC so nested validation, rather than CRC, rejects it.
    for offset in [
        4,
        5,
        6,
        28,
        34,
        36,
        44,
        45,
        46,
        48,
        52,
        56,
        58,
        100,
        106,
        108,
        110,
        155,
        173,
    ]:
        broken = bytearray(original)
        broken[offset] ^= 0x80
        struct.pack_into("!I", broken, len(broken) - 4, zlib.crc32(broken[:-4]))
        with pytest.raises(ValueError):
            core.decode_envelope(bytes(broken))
    for seq in [2**32 - 1, 0, 1]:
        decoded = core.decode_envelope(batch(seq=seq).encode())
        assert decoded.records[0].sequence == seq


@pytest.mark.parametrize("version", [1, 2])
def test_native_rejects_retired_csi_versions(version):
    encoded = bytearray(batch().encode())
    encoded[40 + 60 + 2 + 4] = version
    struct.pack_into("!I", encoded, len(encoded) - 4, zlib.crc32(encoded[:-4]))
    with pytest.raises(ValueError, match="unsupported live CSI header"):
        core.decode_envelope(bytes(encoded))


def test_native_framer_matches_reference_across_every_split():
    raw = encode_serial_frame(24, batch().encode())
    assert decode_serial_frame(raw[1:-1]).payload == batch().encode()
    for split in range(len(raw) + 1):
        d = core.FrameDecoder()
        values = d.feed(raw[:split]) + d.feed(raw[split:])
        assert values == [(24, batch().encode())]
        assert d.malformed_frames == d.oversized_frames == 0
    d = core.FrameDecoder()
    assert not d.feed(b"\0" + b"x" * 3000 + b"\0")
    assert d.oversized_frames == 1
    assert d.feed(raw) == [(24, batch().encode())]
