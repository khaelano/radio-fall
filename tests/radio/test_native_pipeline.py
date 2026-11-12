"""Cross-check native hot paths against preserved Python wire/scientific contracts."""

import ctypes
import json
import os
import random
import struct
import subprocess
import sys
import threading
import time
import zlib
from dataclasses import replace

import numpy as np
import pytest
import serial
from test_gateway import batch, manager

from fall_detection import _radio_native as core
from fall_detection.radio.acquisition.gateway_protocol import GatewayBatch
from fall_detection.radio.acquisition.native import (
    NativeRecord,
    PipelineStats,
    gateway_batch,
)
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


def test_native_rejects_crc_and_identity_reuse_and_preserves_context():
    original = batch().encode()
    bad = bytearray(original)
    bad[-5] ^= 1
    with pytest.raises(ValueError, match="CRC"):
        core.decode_envelope(bytes(bad))
    b = gateway_batch(core.decode_envelope(original))
    r = b.decoded_packet.records[0].record
    updated = r.with_context({"run_id": 123, "capture_host_monotonic_ns": 999})
    assert r.run_id is None and updated.run_id == 123
    assert updated.capture_host_monotonic_ns == 999
    assert updated._native is r._native
    assert b.encode() == original
    assert updated.channel_estimate_block is not None


def test_cached_envelope_is_invalidated_when_batch_is_replaced():
    encoded = batch().encode()
    old = gateway_batch(core.decode_envelope(encoded), encoded=encoded)
    assert old.encode() is encoded
    changed = replace(old, run_id=456)
    assert GatewayBatch.decode(changed.encode()).run_id == 456
    assert changed._encoded is None


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
        GatewayBatch.decode(encoded)


def test_hardware_acquisition_cannot_fall_back_to_python_usb(monkeypatch):
    from types import SimpleNamespace

    from fall_detection.radio.acquisition import gateway_reader

    manager = gateway_reader.GatewayReceiverManager.__new__(
        gateway_reader.GatewayReceiverManager
    )
    manager.serial_factory = None
    monkeypatch.setattr(gateway_reader, "os", SimpleNamespace(name="nt"))
    with pytest.raises(RuntimeError, match="Native gateway acquisition"):
        manager._open_gateway()


@pytest.mark.skipif(os.name != "posix", reason="native POSIX serial reader")
def test_native_manager_records_and_acknowledges_after_validation(tmp_path):
    import pty

    master, slave = pty.openpty()
    port = serial.Serial(os.ttyname(slave), 921600, timeout=0.005)
    os.close(slave)
    accepted = []
    m = manager(tmp_path, lambda record, arrival: accepted.append((record, arrival)))
    m._native_pipeline = core.Pipeline(port.fileno())
    m._usb_buffer = PipelineStats(m._native_pipeline)
    thread = threading.Thread(target=m._read_usb)
    thread.start()
    try:
        raw = b"".join(
            encode_serial_frame(24, batch(seq=i).encode()) for i in range(1, 21)
        )
        source = tmp_path / "wire.bin"
        source.write_bytes(raw)
        producer = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import os,sys,pathlib;p=pathlib.Path(sys.argv[2]).read_bytes();i=0\nwhile i<len(p):i+=os.write(int(sys.argv[1]),p[i:])",
                str(master),
                str(source),
            ],
            pass_fds=(master,),
        )
        assert producer.wait(timeout=2) == 0
        deadline = time.monotonic() + 2
        while (
            len(m.connection.writes) < 20
            and not m.failure
            and time.monotonic() < deadline
        ):
            time.sleep(0.005)
        assert m.failure is None
        assert [r.sequence for r, _ in accepted] == list(range(1, 21))
        assert len(m.connection.writes) == 20
        assert all(isinstance(r, NativeRecord) for r, _ in accepted)
        assert all(r.capture_host_monotonic_ns is not None for r, _ in accepted)
        assert all(r.native_processed_ns >= arrival for r, arrival in accepted)
        assert all(r.transport == "espnow_gateway" for r, _ in accepted)
    finally:
        m._native_pipeline.request_stop()
        thread.join(timeout=2)
        m._native_pipeline.close()
        m.journal.close()
        port.close()
        os.close(master)
    assert not thread.is_alive()


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


@pytest.mark.skipif(os.name != "posix", reason="native POSIX serial reader")
def test_native_reader_decodes_and_preserves_timestamps_during_parent_gil_stall(
    tmp_path,
):
    import pty

    master, slave = pty.openpty()
    port = serial.Serial(os.ttyname(slave), 921600, timeout=0.005)
    os.close(slave)
    pipeline = core.Pipeline(port.fileno())
    payload = b"".join(
        encode_serial_frame(24, batch(seq=i).encode()) for i in range(1, 201)
    )
    source = tmp_path / "wire.bin"
    source.write_bytes(payload)
    producer = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import os,sys,pathlib;p=pathlib.Path(sys.argv[2]).read_bytes();i=0\nwhile i<len(p):i+=os.write(int(sys.argv[1]),p[i:])",
            str(master),
            str(source),
        ],
        pass_fds=(master,),
    )
    frames = []
    try:
        # Hold the real GIL beyond the 200 ms native processing deadline.
        ctypes.PyDLL(None).usleep(ctypes.c_uint(350000))
        resumed = time.monotonic_ns()
        assert producer.wait(timeout=1) == 0
        deadline = time.monotonic() + 2
        while len(frames) < 200 and time.monotonic() < deadline:
            frames.extend(pipeline.frames(256, 0.05))
        assert [f.batch.records[0].sequence for f in frames] == list(range(1, 201))
        assert all(f.arrival_ns < resumed for f in frames)
        assert all(f.processed_ns < resumed for f in frames)
        assert all(f.processed_ns - f.arrival_ns <= 200_000_000 for f in frames)
        stats = json.loads(pipeline.stats_json())
        assert stats["maximum_application_wait_ns"] > 200_000_000
        assert stats["failure"] is None
        pipeline.request_stop()
        pipeline.close()
        assert not pipeline.frames(256, 0)
    finally:
        pipeline.request_stop()
        pipeline.close()
        if producer.poll() is None:
            producer.kill()
        producer.wait()
        port.close()
        os.close(master)


@pytest.mark.skipif(os.name != "posix", reason="native POSIX serial reader")
def test_native_completed_handoff_overflow_is_explicit():
    import pty

    master, slave = pty.openpty()
    port = serial.Serial(os.ttyname(slave), 921600, timeout=0.005)
    os.close(slave)
    pipeline = core.Pipeline(port.fileno(), completed_capacity_bytes=4096)
    try:
        os.write(master, encode_serial_frame(21, b"ok") * 100)
        deadline = time.monotonic() + 1
        while (
            not json.loads(pipeline.stats_json())["failure"]
            and time.monotonic() < deadline
        ):
            time.sleep(0.005)
        with pytest.raises(OSError, match="handoff overflow"):
            pipeline.frames(1, 0)
    finally:
        pipeline.close()
        port.close()
        os.close(master)
