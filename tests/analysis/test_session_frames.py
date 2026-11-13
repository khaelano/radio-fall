"""Check packets, phase boundaries, review refresh, and cache reuse for frames."""

import hashlib
import json
import struct
import zipfile

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("pyarrow")

from journal_builder import RX1, RX2, TX, envelope, mac_text, record

from fall_detection.analysis.diagnostics.phase_signals import phase_signal_from_packets
from fall_detection.analysis.preprocessing.amplitude_pipeline import (
    load_amplitude_session,
)
from fall_detection.analysis.session_frames import load_analysis_session
from fall_detection.radio.phase import HE20_COMPACT_SLOT_INDICES

FOREIGN = bytes.fromhex("020000000001")
RUN = 0xFFFFFFFFFFFFFFFF
SLOTS = np.asarray(HE20_COMPACT_SLOT_INDICES)
VALUES = 40 * np.exp(1j * (0.02 * SLOTS + 0.3))
PAYLOAD_VALUES = np.column_stack((VALUES.imag.round(), VALUES.real.round())).astype(int)
PAYLOAD = bytes(v & 0xFF for v in PAYLOAD_VALUES.ravel())
ORIGINS = {1: 10_000_000_000, 2: 20_000_000_000}


def _json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def _write_journal(root, *, runs=(RUN,), drop_second_attempt_frames=False):
    """Two attempts, two receivers; frames at +0, +10, +20 (and +30, outside)."""
    directory = root / "transport/gateway"
    arrival = {run: 1 for run in runs}
    for position, run in enumerate(runs):
        run_dir = directory / f"{run:016x}"
        run_dir.mkdir(parents=True)
        entries, events = bytearray(), []
        sequence = 0
        for number in (1, 2):
            if position != (number - 1) % len(runs):
                continue
            origin = ORIGINS[number]
            for slot, receiver in enumerate((RX1, RX2)):
                for index, offset in enumerate((0, 10, 20, 30)):
                    frame = record(
                        receiver,
                        sequence,
                        payload=PAYLOAD,
                        sig_mode=4,
                        transmitter=FOREIGN if index == 2 else TX,
                        rx_state=65 if index == 1 else 0,
                        flags=1,
                        radio_us=sequence,
                    )
                    data = envelope(sequence, receiver, [frame], run=run)
                    entries += struct.pack(">QI", arrival[run], len(data)) + data
                    arrival[run] += 1_000
                    events.append(
                        {
                            "kind": "record",
                            "receiver_id": f"rx-{slot + 1}",
                            "sequence": sequence,
                            "receiver_boot_id": 77,
                            "transmitter_boot_id": 9,
                            "capture_host_ns": origin + offset,
                            "clock_uncertainty_us": 100.0,
                            "timely": True,
                        }
                    )
                    sequence += 1
        (run_dir / "envelopes.bin").write_bytes(bytes(entries))
        (run_dir / "events.jsonl").write_text(
            "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in events)
        )


@pytest.fixture
def capture(tmp_path):
    root = tmp_path / "raw" / "sessions" / "test-session"
    _json(
        root / "session.json",
        {
            "artifact_schema_version": 2,
            "session_id": "test-session",
            "status": "complete",
            "protocol_hash": "test-hash",
            "participant_id": "participant-1",
            "environment": {
                "transport": "espnow_gateway",
                "nominal_rate_hz": 100,
                "radio_inventory": {"transmitter": {"mac": mac_text(TX)}},
                "receiver_ids": {mac_text(RX1): "rx-1", mac_text(RX2): "rx-2"},
            },
        },
    )
    _json(
        root / "protocol.json",
        {
            "schema_version": 1,
            "protocol_id": "test",
            "title": "Test",
            "defaults": {
                "countdown_seconds": 1,
                "action_seconds": 1,
                "recovery_seconds": 1,
            },
            "blocks": [
                {
                    "id": "test",
                    "title": "Test",
                    "scenarios": [
                        {
                            "id": "walk",
                            "activity_label": "walk",
                            "title": "Walk",
                            "instruction": "Walk",
                            "repetitions": 1,
                            "attributes": {
                                "start_direction": "front",
                                "end_direction": "front",
                            },
                        }
                    ],
                }
            ],
        },
    )
    events = []
    for number, status in ((1, "invalid"), (2, "accepted")):
        origin = ORIGINS[number]
        _json(
            root / "trials/001_walk" / f"attempt_{number:02d}" / "attempt.json",
            {
                "artifact_schema_version": 2,
                "session_id": "test-session",
                "trial_ordinal": 1,
                "scenario_id": "walk",
                "repetition": 1,
                "activity_label": "walk",
                "status": status,
                "started_monotonic_ns": origin,
                "ended_monotonic_ns": origin + 30,
            },
        )
        for phase, offset in (("countdown", 0), ("action", 10), ("recovery", 20)):
            events.append(
                {
                    "kind": "phase_changed",
                    "trial_ordinal": 1,
                    "attempt": number,
                    "state": phase,
                    "monotonic_ns": origin + offset,
                }
            )
    (root / "events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events)
    )
    _write_journal(root)
    return root, tmp_path / "derived"


def test_packets_keep_capture_phase_boundaries_and_do_not_touch_raw_data(capture):
    root, destination = capture
    before = {
        p: hashlib.sha256(p.read_bytes()).digest()
        for p in root.rglob("*")
        if p.is_file()
    }
    session = load_analysis_session(root, destination)
    packets = session.read_packets()
    assert len(session.attempts) == 2
    assert len(session.phases) == 6
    # The window is half open, so the frame captured at +30 belongs to no attempt.
    assert len(packets) == 12
    assert set(packets.receiver_id) == {"rx-1", "rx-2"}
    one = packets.loc[packets.attempt.eq(2) & packets.receiver_id.eq("rx-1")]
    assert one.phase.tolist() == ["preparation", "action", "resting"]
    assert one.collection_phase.tolist() == ["countdown", "action", "recovery"]
    assert one.driver_valid.tolist() == [True, False, True]
    assert one.is_sensing.tolist() == [True, True, False]
    assert one.run_id.iloc[0] == str(RUN)
    assert one.transmitter_boot_id.iloc[0] == "9"
    assert one.first_word.tolist() == [1, 1, 1]
    np.testing.assert_array_equal(
        one.iloc[0].csi_i, np.frombuffer(PAYLOAD, np.int8)[1::2]
    )
    np.testing.assert_array_equal(
        one.iloc[0].csi_q, np.frombuffer(PAYLOAD, np.int8)[0::2]
    )
    assert one.time_seconds.tolist() == [0.0, 1e-8, 2e-8]
    assert all(
        hashlib.sha256(p.read_bytes()).digest() == digest
        for p, digest in before.items()
    )


def test_missing_string_attempt_value_reads_as_null(capture):
    root, destination = capture
    session = load_analysis_session(root, destination)
    # Sessions that mix present and missing directions (for example a walk-to-
    # stand scenario without an end direction) give a pandas string column whose
    # missing value is NaN rather than None.
    session.attempts["end_direction"] = pd.Series(
        ["front", None], index=session.attempts.index, dtype="str"
    )
    assert isinstance(session.attempts["end_direction"].iloc[1], float)

    packets = session.read_packets(attempt_key=session.attempts.iloc[1].attempt_key)

    assert len(packets) > 0
    assert packets["end_direction"].isna().all()
    assert packets["start_direction"].eq("front").all()


def test_packets_are_sorted_by_capture_time_and_decode_as_phase_signals(capture):
    root, destination = capture
    session = load_analysis_session(root, destination)
    key = session.attempts.iloc[1].attempt_key
    selected = session.read_packets(attempt_key=key, receiver_id="rx-1")
    signal = phase_signal_from_packets(selected)
    assert signal.time_seconds.tolist() == [0.0, 1e-8]  # the foreign frame is excluded
    assert signal.complex_csi.shape[0] == 2
    np.testing.assert_allclose(np.abs(signal.complex_csi[0, :3]), 40, atol=1)
    action = session.read_packets(
        phase="action", columns=["receiver_id", "csi_i", "status"]
    )
    assert len(action) == 4
    assert list(action) == ["receiver_id", "csi_i", "status"]


def test_attempt_directory_without_metadata_is_ignored(capture):
    root, destination = capture
    baseline = len(load_analysis_session(root, destination).attempts)
    orphan = root / "trials/001_walk/attempt_03"
    orphan.mkdir()
    (orphan / "notes.txt").write_text("crash before attempt.json")

    session = load_analysis_session(root, destination)

    assert len(session.attempts) == baseline


def test_unknown_columns_and_attempts_are_rejected(capture):
    root, destination = capture
    session = load_analysis_session(root, destination)
    with pytest.raises(KeyError):
        session.packets(session.attempts.iloc[0].attempt_key, "rx-1", ["nope"])
    with pytest.raises(KeyError):
        session.packets("trials/999_none/attempt_01", "rx-1")


def test_unchanged_tables_are_not_converted_again(capture):
    root, destination = capture
    load_analysis_session(root, destination)
    stamp = (destination / "frames.parquet").stat().st_mtime_ns
    assert load_analysis_session(root, destination).manifest["packet_count"] == 12
    assert (destination / "frames.parquet").stat().st_mtime_ns == stamp


def test_review_changes_refresh_labels_and_fingerprint(capture):
    root, destination = capture
    first = load_analysis_session(root, destination)
    key = first.attempts.iloc[1].attempt_key
    _json(
        root / "session_review.json",
        {
            "schema_version": 1,
            "session_id": "test-session",
            "protocol_hash": "test-hash",
            "revision": 1,
            "attempts": {
                key: {
                    "activity_label": "corrected",
                    "inclusion": "exclude",
                    "quality": "bad",
                }
            },
        },
    )
    second = load_analysis_session(root, destination)
    assert second.manifest["source_fingerprint"] != first.manifest["source_fingerprint"]
    rows = second.read_packets(attempt_key=key)
    assert rows.activity_label.eq("corrected").all()
    assert rows.original_activity_label.eq("walk").all()
    assert rows.inclusion.eq("exclude").all()
    assert rows.quality.eq("bad").all()
    # Changing only review state must not convert the raw journals again.
    assert second.frames.source_fingerprint == first.frames.source_fingerprint


def test_empty_phase_intervals_are_preserved(capture):
    root, destination = capture
    # No capture occurs between +15 and +20; the action interval still exists.
    path = root / "events.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    for event in events:
        if event["state"] == "action":
            event["monotonic_ns"] += 5
    path.write_text("".join(json.dumps(event) + "\n" for event in events))
    session = load_analysis_session(root, destination)
    assert len(session.phases.loc[session.phases.phase.eq("action")]) == 2
    assert session.read_packets(phase="action").empty


@pytest.mark.parametrize("problem", ["corrupt_journal", "duplicate_phase"])
def test_invalid_input_is_refused(capture, problem):
    root, destination = capture
    if problem == "corrupt_journal":
        journal = next(root.glob("transport/gateway/*/envelopes.bin"))
        data = bytearray(journal.read_bytes())
        data[60] ^= 0xFF
        journal.write_bytes(bytes(data))
        expected = RuntimeError
    else:
        path = root / "events.jsonl"
        with path.open("a") as stream:
            stream.write(path.read_text().splitlines()[0] + "\n")
        expected = ValueError
    with pytest.raises(expected):
        load_analysis_session(root, destination)


def test_attempt_spanning_two_transmitter_epochs_is_refused(tmp_path, capture):
    root, destination = capture
    # Re-record attempt 2 across two runs, as after a gateway reconnect.
    for run_dir in (root / "transport/gateway").iterdir():
        for path in run_dir.iterdir():
            path.unlink()
        run_dir.rmdir()
    _write_journal(root, runs=(RUN, RUN - 1))
    session = load_analysis_session(root, destination)
    for key in session.attempts.attempt_key:
        # Each attempt is wholly inside one run in this layout.
        assert session.packets(key, "rx-1").num_rows == 3


def test_requires_transmitter_and_rate(capture):
    root, destination = capture
    manifest = json.loads((root / "session.json").read_text())
    del manifest["environment"]["radio_inventory"]
    _json(root / "session.json", manifest)
    session = load_analysis_session(root, destination)
    with pytest.raises(ValueError, match="transmitter MAC"):
        session.packets(session.attempts.iloc[0].attempt_key, "rx-1")


def test_refuses_raw_destination_and_active_sessions(capture):
    root, destination = capture
    with pytest.raises(ValueError, match="outside raw"):
        load_analysis_session(root, root / "frames")
    path = root / "session.json"
    manifest = json.loads(path.read_text())
    manifest["status"] = "open"
    _json(path, manifest)
    with pytest.raises(ValueError, match="closed session"):
        load_analysis_session(root, destination)


def test_amplitude_session_exposes_polars_attempts(capture):
    import polars as pl

    root, destination = capture
    actual = load_amplitude_session(root, destination, progress=None)
    assert isinstance(actual.attempts, pl.DataFrame)
    assert len(actual.attempts) == 2
    assert actual.manifest["session_id"] == "test-session"
    with pytest.raises(ValueError, match="outside raw"):
        load_amplitude_session(root, root / "frames", progress=None)


def test_archive_source_matches_directory_source(tmp_path, capture):
    root, destination = capture
    expected = load_analysis_session(root, destination / "directory").read_packets()
    archive = root.parent / "test-session.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                bundle.write(path, "original/" + path.relative_to(root).as_posix())
    from_archive = load_analysis_session(archive, destination / "archive")
    assert from_archive.manifest["source_directory"] == str(archive)
    import pandas as pd

    pd.testing.assert_frame_equal(from_archive.read_packets(), expected)
    assert not list(destination.glob(".manifests-*"))


def test_recording_summary_matches_per_recording_packets(capture):
    root, destination = capture
    session = load_analysis_session(root, destination)
    summary = session.recording_summary().set_index(["attempt_key", "receiver_id"])
    assert len(summary) == 4
    for attempt in session.attempts.itertuples(index=False):
        for receiver in ("rx-1", "rx-2"):
            packets = session.packets(attempt.attempt_key, receiver).to_pandas()
            sensing = packets.loc[packets.is_sensing]
            row = summary.loc[(attempt.attempt_key, receiver)]
            assert row.packets == len(sensing) == 2
            assert row.driver_valid_packets == int(sensing.driver_valid.sum()) == 1
            assert row.first_ns == sensing.capture_time_ns.min()
            assert row.last_ns == sensing.capture_time_ns.max()
    only = session.recording_summary([session.attempts.iloc[0].attempt_key])
    assert set(only.attempt_key) == {session.attempts.iloc[0].attempt_key}


def test_empty_and_populated_recordings_share_a_schema(capture):
    root, destination = capture
    session = load_analysis_session(root, destination)
    key = session.attempts.iloc[0].attempt_key
    populated = session.packets(key, "rx-1")
    session.attempt_indices[key]  # the attempt exists
    empty = session.packets(key, "rx-9")  # no such receiver: no frames
    assert empty.num_rows == 0
    assert empty.schema == populated.schema
    import polars as pl

    assert pl.concat([pl.from_arrow(populated), pl.from_arrow(empty)]).height == 3


def test_notebook_sequence_columns_are_all_available(capture):
    from fall_detection.analysis.preprocessing.sequence_preprocessing import (
        SEQUENCE_COLUMNS,
    )

    root, destination = capture
    session = load_analysis_session(root, destination)
    key = session.attempts.iloc[0].attempt_key
    table = session.packets(key, "rx-1", SEQUENCE_COLUMNS)
    assert table.column_names == SEQUENCE_COLUMNS
    assert table.num_rows == 3


def test_parquet_style_filters_choose_recordings_and_rows(capture):
    root, destination = capture
    session = load_analysis_session(root, destination)
    selected = session.read_packets(
        filters=[("attempt", "==", 2), ("receiver_id", "==", "rx-1")]
    )
    assert len(selected) == 3
    assert set(selected.receiver_id) == {"rx-1"}
    action = session.read_packets(
        filters=[("phase", "==", "action"), ("status", "==", "accepted")],
        columns=["receiver_id", "csi_i"],
        arrow_backed=True,
    )
    assert len(action) == 2
    assert list(action) == ["receiver_id", "csi_i"]
    assert "pyarrow" in str(action.dtypes.iloc[0])
    both = session.read_packets(
        filters=[("receiver_id", "in", ["rx-1", "rx-2"]), ("sequence", ">=", 0)]
    )
    assert len(both) == 12
    with pytest.raises(ValueError, match="operator"):
        session.read_packets(filters=[("attempt", "~", 2)])


def test_payload_helpers_handle_fixed_variable_and_sliced_columns():
    import pyarrow as pa

    from fall_detection.analysis.session_frames import _int16_lists, _payload_bytes

    rows = [bytes([1, 2, 3, 4]), bytes([5, 6]), bytes([7, 8, 9, 10, 11, 12])]
    variable = pa.array(rows, type=pa.binary())
    values, offsets = _payload_bytes(variable)
    assert values.tolist() == list(range(1, 13)) and offsets.tolist() == [0, 4, 6, 12]
    # Imaginary bytes come first, real bytes second, within every row.
    real = _int16_lists(values[1::2], offsets // 2).to_pylist()
    imag = _int16_lists(values[0::2], offsets // 2).to_pylist()
    assert real == [[2, 4], [6], [8, 10, 12]]
    assert imag == [[1, 3], [5], [7, 9, 11]]
    # A slice keeps its offsets relative to the first retained row.
    values, offsets = _payload_bytes(variable.slice(1, 2))
    assert values.tolist() == [5, 6, 7, 8, 9, 10, 11, 12]
    assert offsets.tolist() == [0, 2, 8]
    fixed = pa.FixedSizeBinaryArray.from_buffers(
        pa.binary(4), 3, [None, pa.py_buffer(bytes(range(12)))]
    )
    values, offsets = _payload_bytes(fixed.slice(1, 2))
    assert values.tolist() == [4, 5, 6, 7, 8, 9, 10, 11]
    assert offsets.tolist() == [0, 4, 8]
    chunked = pa.chunked_array([variable.slice(0, 1), variable.slice(1, 2)])
    assert _payload_bytes(chunked)[0].tolist() == list(range(1, 13))
