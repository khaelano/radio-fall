"""Check packet preservation, phase boundaries, filtering, and cache reuse."""

import csv
import hashlib
import json

import numpy as np
import pytest

pytest.importorskip("pyarrow")

from fall_detection.analysis.phase_signals import (
    load_phase_signal,
    phase_signal_from_packets,
)
from fall_detection.analysis.session_parquet import load_parquet_session
from fall_detection.radio.preprocessing.phase import HE20_COMPACT_SLOT_INDICES


def _json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def _csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def capture(tmp_path):
    root = tmp_path / "raw" / "sessions" / "test-session"
    _json(root / "session.json", {
        "artifact_schema_version": 2, "session_id": "test-session",
        "status": "complete", "protocol_hash": "test-hash",
        "participant_id": "participant-1",
        "environment": {
            "transport": "espnow_gateway", "nominal_rate_hz": 100,
            "radio_inventory": {"transmitter": {"mac": "aa:bb:cc:dd:ee:ff"}},
        },
    })
    _json(root / "protocol.json", {
        "schema_version": 1, "protocol_id": "test", "title": "Test",
        "defaults": {"countdown_seconds": 1, "action_seconds": 1,
                     "recovery_seconds": 1},
        "blocks": [{"id": "test", "title": "Test", "scenarios": [{
            "id": "walk", "activity_label": "walk", "title": "Walk",
            "instruction": "Walk", "repetitions": 1,
            "attributes": {"start_direction": "front", "end_direction": "front"},
        }]}],
    })
    events = []
    slots = np.asarray(HE20_COMPACT_SLOT_INDICES)
    values = 40 * np.exp(1j * (0.02 * slots + 0.3))
    payload = np.column_stack((values.imag.round(), values.real.round())).astype(int)
    for number, status in ((1, "invalid"), (2, "accepted")):
        directory = root / "trials/001_walk" / f"attempt_{number:02d}"
        origin = number * 10_000_000_000
        _json(directory / "attempt.json", {
            "artifact_schema_version": 2, "session_id": "test-session",
            "trial_ordinal": 1, "scenario_id": "walk", "repetition": 1,
            "activity_label": "walk", "status": status,
            "started_monotonic_ns": origin, "ended_monotonic_ns": origin + 30,
        })
        for phase, offset in (("countdown", 0), ("action", 10), ("recovery", 20)):
            events.append({"kind": "phase_changed", "trial_ordinal": 1,
                           "attempt": number, "state": phase,
                           "monotonic_ns": origin + offset})
        for receiver_id in ("rx-1", "rx-2"):
            receiver = directory / "receivers" / receiver_id
            csi, timing, sidecar = [], [], []
            for index, offset in enumerate((0, 10, 20, 30)):
                csi.append({
                    "type": "CSI_DATA", "id": index,
                    "mac": "aa:bb:cc:dd:ee:ff" if index < 3 else "foreign",
                    "sig_mode": 4, "mcs": 0, "bandwidth": 0, "stbc": 0,
                    "first_word": 1, "local_timestamp": index,
                    "len": payload.size, "data": json.dumps(payload.ravel().tolist()),
                    "rx_state": 0 if index != 1 else 65, "rssi": -50,
                    "noise_floor": -95,
                })
                timing.append({
                    "sequence": index, "rx_radio_timestamp_us": index,
                    "host_receive_monotonic_ns": origin + offset + 1_000_000,
                })
                sidecar.append({
                    "schema_version": 1, "sequence": index,
                    "rx_radio_timestamp_us": index, "run_id": "18446744073709551615",
                    "transmitter_boot_id": 4, "receiver_boot_id": 5,
                    "capture_host_monotonic_ns": origin + offset,
                    "clock_uncertainty_us": 100,
                })
            _csv(receiver / "csi.csv", csi)
            _csv(receiver / "radio_timing.csv", timing)
            (receiver / "gateway_timing.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in sidecar)
            )
    (root / "events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events)
    )
    return root, tmp_path / "derived"


def test_load_parquet_session_preserves_packets_and_capture_phase_boundaries(capture):
    root, destination = capture
    before = {p: hashlib.sha256(p.read_bytes()).digest()
              for p in root.rglob("*") if p.is_file()}
    exported = load_parquet_session(root, destination)
    packets = exported.read_packets()
    assert len(exported.attempts) == 2
    assert len(exported.phases) == 6
    assert len(packets) == 16
    assert set(packets.receiver_id) == {"rx-1", "rx-2"}
    one = packets.loc[packets.attempt.eq(2) & packets.receiver_id.eq("rx-1")]
    assert one.phase.tolist() == ["preparation", "action", "resting", "unassigned"]
    assert one.collection_phase.tolist() == ["countdown", "action", "recovery", "unassigned"]
    assert one.driver_valid.tolist() == [True, False, True, True]
    assert one.is_sensing.tolist() == [True, True, True, False]
    assert one.run_id.iloc[0] == "18446744073709551615"
    source = next(root.glob("trials/*/attempt_02/receivers/rx-1/csi.csv"))
    payload = json.loads(next(csv.DictReader(source.open()))["data"])
    np.testing.assert_array_equal(one.iloc[0].csi_i, payload[1::2])
    np.testing.assert_array_equal(one.iloc[0].csi_q, payload[0::2])
    assert all(hashlib.sha256(p.read_bytes()).digest() == digest
               for p, digest in before.items())


def test_load_parquet_session_filters_before_loading_and_decodes_like_csv(capture):
    root, destination = capture
    exported = load_parquet_session(root, destination)
    selected = exported.read_packets(filters=[
        ("attempt", "==", 2), ("receiver_id", "==", "rx-1"),
    ])
    actual = phase_signal_from_packets(selected)
    expected = load_phase_signal(root, "001/02", "rx-1")
    for name in ("time_seconds", "complex_csi", "raw_phase", "calibrated_phase"):
        np.testing.assert_allclose(getattr(actual, name), getattr(expected, name))
    action = exported.read_packets(
        filters=[("phase", "==", "action"), ("status", "==", "accepted")],
        columns=["receiver_id", "csi_i"], arrow_backed=True,
    )
    assert len(action) == 2
    assert list(action) == ["receiver_id", "csi_i"]
    assert "pyarrow" in str(action.dtypes.iloc[0])


def test_load_parquet_session_reuses_unchanged_export(capture, monkeypatch):
    root, destination = capture
    load_parquet_session(root, destination)
    def fail(*args):
        raise AssertionError("unchanged CSVs should not be read")
    monkeypatch.setattr("fall_detection.analysis.phase_signals.load_capture_packets", fail)
    assert load_parquet_session(root, destination).manifest["packet_count"] == 16


def test_load_parquet_session_refreshes_review_fields(capture):
    root, destination = capture
    first = load_parquet_session(root, destination)
    key = first.attempts.iloc[1].attempt_key
    _json(root / "session_review.json", {
        "schema_version": 1, "session_id": "test-session", "protocol_hash": "test-hash",
        "revision": 1, "attempts": {key: {
            "activity_label": "corrected", "inclusion": "exclude", "quality": "bad",
        }},
    })
    second = load_parquet_session(root, destination)
    assert second.manifest["source_fingerprint"] != first.manifest["source_fingerprint"]
    rows = second.read_packets(filters=[("attempt", "==", 2)])
    assert rows.activity_label.eq("corrected").all()
    assert rows.original_activity_label.eq("walk").all()
    assert rows.inclusion.eq("exclude").all()
    assert rows.quality.eq("bad").all()


def test_load_parquet_session_preserves_empty_phase_intervals(capture):
    root, destination = capture
    # No capture occurs between +15 and +20; the action interval still exists.
    path = root / "events.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    for event in events:
        if event["state"] == "action":
            event["monotonic_ns"] += 5
    path.write_text("".join(json.dumps(event) + "\n" for event in events))
    exported = load_parquet_session(root, destination)
    assert len(exported.phases.loc[exported.phases.phase.eq("action")]) == 2
    assert exported.read_packets(filters=[("phase", "==", "action")]).empty


@pytest.mark.parametrize("problem", ["missing_sidecar", "misaligned", "duplicate_phase"])
def test_load_parquet_session_refuses_invalid_input(capture, problem):
    root, destination = capture
    receiver = next(root.glob("trials/*/attempt_01/receivers/rx-1"))
    if problem == "missing_sidecar":
        (receiver / "gateway_timing.jsonl").unlink()
    elif problem == "misaligned":
        path = receiver / "radio_timing.csv"
        rows = list(csv.DictReader(path.open()))
        rows[0]["sequence"] = 999
        _csv(path, rows)
    else:
        path = root / "events.jsonl"
        with path.open("a") as stream:
            stream.write(path.read_text().splitlines()[0] + "\n")
    with pytest.raises(ValueError):
        load_parquet_session(root, destination)
    assert not (destination / "session.json").exists()


def test_load_parquet_session_refuses_raw_destination_and_active_sessions(capture):
    root, destination = capture
    with pytest.raises(ValueError, match="outside raw"):
        load_parquet_session(root, root / "parquet")
    path = root / "session.json"
    manifest = json.loads(path.read_text())
    manifest["status"] = "open"
    _json(path, manifest)
    with pytest.raises(ValueError, match="closed session"):
        load_parquet_session(root, destination)


def test_amplitude_session_reuses_valid_export_without_pandas_tables(capture, monkeypatch):
    import pandas as pd
    import polars as pl
    from fall_detection.analysis.amplitude_pipeline import load_amplitude_session

    root, destination = capture
    load_parquet_session(root, destination)

    def forbidden(*args, **kwargs):
        raise AssertionError("Cached amplitude path should load its tables in Polars")

    monkeypatch.setattr(pd, "read_parquet", forbidden)
    actual = load_amplitude_session(root, destination, progress=None)
    assert isinstance(actual.attempts, pl.DataFrame)
    assert len(actual.attempts) == 2
    with pytest.raises(ValueError, match="outside raw"):
        load_amplitude_session(root, root / "parquet", progress=None)
