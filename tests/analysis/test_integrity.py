"""Exercise the shared integrity interface with tiny deterministic sessions."""

import csv
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest

from fall_detection.analysis import analyze_latest_session, analyze_session
from fall_detection.analysis import _receiver
from fall_detection.radio.preprocessing.phase import (
    HE20_COMPACT_SLOT_INDICES,
    HE20_SLOT_INDICES,
    HT20_SLOT_INDICES,
    decode_ltf_blocks,
    phase_slot_mask,
)

_TX = "aa:bb:cc:dd:ee:ff"


def _json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def session(tmp_path):
    root = tmp_path / "data/raw/sessions/20261026T000000000000Z"
    _json(
        root / "session.json",
        {
            "artifact_schema_version": 2,
            "session_id": root.name,
            "protocol_hash": "test",
            "status": "complete",
            "started_at_utc": "2026-10-26T00:00:00+00:00",
            "environment": {
                "receiver_bindings": {"rx-1": {}, "rx-2": {}},
                "nominal_rate_hz": 100,
                "radio_inventory": {"transmitter": {"mac": _TX}},
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
                "action_seconds": 2,
                "recovery_seconds": 1,
            },
            "blocks": [
                {
                    "id": "block",
                    "title": "Block",
                    "scenarios": [
                        {
                            "id": "sit",
                            "activity_label": "sit",
                            "title": "Sit",
                            "instruction": "Sit down",
                            "repetitions": 1,
                        }
                    ],
                }
            ],
        },
    )
    attempt = root / "trials/001_sit/attempt_01"
    _json(
        attempt / "attempt.json",
        {
            "artifact_schema_version": 2,
            "trial_ordinal": 1,
            "activity_label": "sit",
            "status": "accepted",
            "action_confirmed": True,
            "started_monotonic_ns": 1_000_000_000,
            "ended_monotonic_ns": 3_250_000_000,
        },
    )
    events = [
        {"kind": "attempt_started", "monotonic_ns": 1_000_000_000},
        {"kind": "phase_changed", "state": "countdown", "monotonic_ns": 1_000_000_000},
        {"kind": "phase_changed", "state": "action", "monotonic_ns": 2_000_000_000},
        {"kind": "action_confirmed", "monotonic_ns": 2_250_000_000},
        {"kind": "phase_changed", "state": "recovery", "monotonic_ns": 2_250_000_000},
        {
            "kind": "trial_resolved",
            "disposition": "accepted",
            "monotonic_ns": 3_250_000_000,
        },
    ]
    for event in events:
        event.update(trial_ordinal=1, attempt=1)
    (root / "events.jsonl").write_text(
        "\n".join(map(json.dumps, events)), encoding="utf-8"
    )
    csi_rows, timing_rows = [], []
    for sequence, tick, host in zip(
        [10, 11, 13, 99],
        [2**32 - 10_000, 0, 20_000, 25_000],
        [1_500_000_000, 2_100_000_000, 2_500_000_000, 3_000_000_000],
    ):
        payload = [value for _ in HE20_COMPACT_SLOT_INDICES for value in (0, 20)]
        if sequence == 11:
            payload[5] = 2  # Physical subcarrier +2 falls below amplitude 4.
        csi_rows.append(
            {
                "id": sequence,
                "mac": _TX if sequence != 99 else "foreign",
                "sig_mode": 4,
                "mcs": 0,
                "bandwidth": 0,
                "local_timestamp": tick,
                "len": len(payload),
                "stbc": 0,
                "first_word": 0,
                "data": json.dumps(payload),
            }
        )
        timing_rows.append(
            {
                "sequence": sequence,
                "rx_radio_timestamp_us": tick,
                "host_receive_monotonic_ns": host,
            }
        )
    _csv(attempt / "receivers/rx-1/csi.csv", csi_rows)
    _csv(attempt / "receivers/rx-1/radio_timing.csv", timing_rows)
    return root


def test_analyze_session_counts_loss_wraps_masking_and_phases(session):
    raw_before = {
        path: hashlib.sha256(path.read_bytes()).digest()
        for path in session.rglob("*")
        if path.is_file()
    }
    report = analyze_session(session)
    receiver = report.receivers.set_index("receiver_id").loc["rx-1"]
    assert receiver["raw_csi_rows"] == 4
    assert receiver["sensing_link_csi_rows"] == 3
    assert receiver["sequence_gap_missing_frames"] == 1
    assert receiver["sequence_gap_loss_pct"] == 25
    assert receiver["effective_sampling_rate_hz"] == pytest.approx(2 / 0.03)
    assert receiver["timestamp_gap_intervals"] == 1
    assert receiver["mean_usable_subcarriers_per_packet"] == pytest.approx(242 - 1 / 3)
    assert report.receiver_attempts.iloc[0]["timestamp_wraps"] == 1
    assert report.receiver_issues["receiver_id"].tolist() == ["rx-2"]
    assert report.phase_issues.empty
    assert report.phase_packet_counts.query("receiver_id == 'rx-1'")[
        "sensing_link_csi_rows"
    ].tolist() == [1, 1, 1]
    assert report.phase_attempts.iloc[0]["action_seconds"] == pytest.approx(0.25)
    assert report.attempt_counts.loc["sit", "accepted"] == 1
    assert all(
        hashlib.sha256(path.read_bytes()).digest() == digest
        for path, digest in raw_before.items()
    )


@pytest.mark.parametrize(
    "slots,sig_mode,stbc",
    [
        (HE20_SLOT_INDICES, 4, 0),
        (HE20_COMPACT_SLOT_INDICES, 4, 0),
        (HT20_SLOT_INDICES, 1, 0),
        (HT20_SLOT_INDICES * 2, 1, 0),
        (HT20_SLOT_INDICES * 3, 1, 1),
    ],
)
@pytest.mark.parametrize("first_word", [False, True])
def test_phase_slot_mask_matches_canonical_decoder(slots, sig_mode, stbc, first_word):
    values = tuple(complex(20, 0) for _ in slots)
    blocks = decode_ltf_blocks(
        values, sig_mode=sig_mode, bandwidth=0, stbc=stbc, first_word_invalid=first_word
    )
    actual = phase_slot_mask(
        sig_mode=sig_mode,
        bandwidth=0,
        stbc=stbc,
        pair_count=len(values),
        first_word_invalid=first_word,
    )
    expected = tuple(
        bool(np.isfinite(value)) for block in blocks for value in block.raw_phases
    )
    assert actual == expected


def test_analyze_session_cache_hits_and_invalidates_changed_receiver(
    session, tmp_path, monkeypatch
):
    cache = tmp_path / "cache"
    initial = analyze_session(session, cache_dir=cache)
    original_scan = _receiver.scan_receiver
    calls = []

    def tracked(*args, **kwargs):
        calls.append(args[0])
        return original_scan(*args, **kwargs)

    monkeypatch.setattr(_receiver, "scan_receiver", tracked)
    cached = analyze_session(session, cache_dir=cache)
    assert not calls
    assert cached.overview.iloc[0]["cached_receiver_recordings"] == 2
    pd.testing.assert_frame_equal(initial.receiver_attempts, cached.receiver_attempts)
    path = next(session.glob("trials/*/attempt_*/receivers/rx-1/csi.csv"))
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[0]["data"] = "[broken JSON]"
    _csv(path, rows)
    changed = analyze_session(session, cache_dir=cache)
    assert len(calls) == 1
    assert changed.overview.iloc[0]["cached_receiver_recordings"] == 1
    assert changed.receivers.iloc[0]["phase_mask_unreadable_rows"] == 1
    calls.clear()
    analyze_session(session, cache_dir=cache, refresh=True)
    assert len(calls) == 2


def test_analyze_session_cache_reconstructs_changed_events(session, tmp_path):
    cache = tmp_path / "cache"
    analyze_session(session, cache_dir=cache)
    path = session / "events.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    events[2]["monotonic_ns"] = 2_200_000_000
    path.write_text("\n".join(map(json.dumps, events)))
    changed = analyze_session(session, cache_dir=cache)
    assert changed.overview.iloc[0]["cached_receiver_recordings"] == 0
    assert changed.phase_packet_counts.query("receiver_id == 'rx-1'")[
        "sensing_link_csi_rows"
    ].tolist() == [2, 0, 1]


def test_analyze_session_partial_invalid_attempt_does_not_require_confirmation(session):
    path = next(session.glob("trials/*/attempt_*/attempt.json"))
    manifest = json.loads(path.read_text())
    manifest.update(
        status="invalid", action_confirmed=False, ended_monotonic_ns=2_400_000_000
    )
    _json(path, manifest)
    events_path = session / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text().splitlines()][:3]
    events_path.write_text("\n".join(map(json.dumps, events)))
    report = analyze_session(session)
    assert report.phase_issues.empty
    assert report.phase_attempts.iloc[0]["phase_sequence"] == "countdown → action"


def test_analyze_session_rejects_cache_in_raw_data(session):
    with pytest.raises(ValueError, match="outside raw"):
        analyze_session(session, cache_dir=session.parent.parent / "cache")


def test_analyze_session_header_only_missing_and_unmatched_timing(session):
    csi = next(session.glob("trials/*/attempt_*/receivers/rx-1/csi.csv"))
    csi.write_text(csi.read_text().splitlines()[0] + "\n")
    report = analyze_session(session)
    assert report.receivers.iloc[0]["empty_csi_attempts"] == 1
    assert report.receiver_attempts.iloc[0]["row_count_difference"] == -4
    csi.unlink()
    report = analyze_session(session)
    assert report.receivers.iloc[0]["csi_files_missing"] == 1
    assert report.receiver_attempts.iloc[0]["timing_rows"] == 4


def test_analyze_latest_session_uses_manifest_start_time(session):
    earlier = session.parent / "zzzz-earlier"
    shutil.copytree(session, earlier)
    path = earlier / "session.json"
    manifest = json.loads(path.read_text())
    manifest["started_at_utc"] = "2026-01-01T00:00:00+00:00"
    _json(path, manifest)
    assert analyze_latest_session(session.parent).session_dir == session


def test_analyze_session_handles_no_attempts(session):
    shutil.rmtree(session / "trials")
    report = analyze_session(session)
    assert report.attempts.empty
    assert report.receiver_issues.empty
    assert report.phase_issues.empty
    assert report.trial_coverage.iloc[0]["planned_trials_never_started"] == 1


def test_analyze_session_ignores_corrupt_cache_and_active_sessions(session, tmp_path):
    cache = tmp_path / "cache"
    analyze_session(session, cache_dir=cache)
    for path in cache.glob("*.json"):
        path.write_text("broken")
    repaired = analyze_session(session, cache_dir=cache)
    assert repaired.overview.iloc[0]["cached_receiver_recordings"] == 0
    path = session / "session.json"
    manifest = json.loads(path.read_text())
    manifest["status"] = "open"
    _json(path, manifest)
    active = analyze_session(session, cache_dir=cache)
    assert active.overview.iloc[0]["cached_receiver_recordings"] == 0


def test_analyze_session_parallel_scan_matches_serial(session):
    serial = analyze_session(session)
    parallel = analyze_session(session, workers=2)
    pd.testing.assert_frame_equal(serial.receiver_attempts, parallel.receiver_attempts)
    pd.testing.assert_frame_equal(
        serial.phase_packet_counts, parallel.phase_packet_counts
    )


def test_analyze_session_rejects_invalid_worker_count(session):
    with pytest.raises(ValueError, match="positive integer"):
        analyze_session(session, workers=0)
