"""Exercise the shared integrity interface with tiny deterministic sessions."""

import hashlib
import json
import os
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pa = pytest.importorskip("pyarrow")

from journal_builder import FOREIGN, RX1, TX, write_session

from fall_detection.analysis import _receiver, analyze_latest_session, analyze_session
from fall_detection.analysis.session_frames import load_analysis_session
from fall_detection.radio.preprocessing.phase import (
    HE20_COMPACT_SLOT_INDICES,
    HE20_SLOT_INDICES,
    HT20_SLOT_INDICES,
    decode_ltf_blocks,
    phase_slot_mask,
)

_EVENTS = [
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
for _event in _EVENTS:
    _event.update(trial_ordinal=1, attempt=1)
_ATTEMPT = {
    "trial_ordinal": 1,
    "activity_label": "sit",
    "status": "accepted",
    "action_confirmed": True,
    "started_monotonic_ns": 1_000_000_000,
    "ended_monotonic_ns": 3_250_000_000,
}


def _json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _frames():
    frames = []
    for sequence, tick, capture in zip(
        [10, 11, 13, 99],
        [2**32 - 10_000, 0, 20_000, 25_000],
        [1_500_000_000, 2_100_000_000, 2_500_000_000, 3_000_000_000],
    ):
        payload = [value for _ in HE20_COMPACT_SLOT_INDICES for value in (0, 20)]
        if sequence == 11:
            payload[5] = 2  # Physical subcarrier +2 falls below amplitude 4.
        frames.append(
            {
                "receiver": RX1,
                "sequence": sequence,
                "capture_ns": capture,
                "payload": bytes(payload),
                "sig_mode": 4,
                "radio_us": tick,
                "transmitter": TX if sequence != 99 else FOREIGN,
            }
        )
    return frames


def _build(tmp_path, frames=None, events=None, **options):
    """Write a session directory; frames default to four rx-1 packets."""
    return write_session(
        tmp_path / "data/raw/sessions/20261026T000000000000Z",
        attempts=options.pop("attempts", [dict(_ATTEMPT)]),
        events=_EVENTS if events is None else events,
        frames=_frames() if frames is None else frames,
        extra_session={"started_at_utc": "2026-10-26T00:00:00+00:00"},
        **options,
    )


def _load(root):
    return load_analysis_session(root, root.parents[3] / "derived" / root.name)


@pytest.fixture
def session(tmp_path):
    return _load(_build(tmp_path))


def _root(session) -> Path:
    return Path(session.manifest["source_directory"])


def test_analyze_session_counts_loss_wraps_masking_and_phases(session):
    root = _root(session)
    raw_before = {
        path: hashlib.sha256(path.read_bytes()).digest()
        for path in root.rglob("*")
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
    assert receiver["attempts_without_frames"] == 0
    assert report.receiver_attempts.iloc[0]["timestamp_wraps"] == 1
    assert report.receiver_issues["receiver_id"].tolist() == ["rx-2"]
    assert report.phase_issues.empty
    assert report.phase_packet_counts.query("receiver_id == 'rx-1'")[
        "sensing_link_csi_rows"
    ].tolist() == [1, 1, 1]
    assert report.phase_attempts.iloc[0]["action_seconds"] == pytest.approx(0.25)
    assert report.attempt_counts.loc["sit", "accepted"] == 1
    assert report.session_dir == root
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


def test_analyze_session_cache_hits_and_invalidates_changed_frame_tables(
    session, tmp_path, monkeypatch
):
    cache = tmp_path / "cache"
    initial = analyze_session(session, cache_dir=cache)
    original_scan = _receiver.scan_receiver
    calls = []

    def tracked(*args, **kwargs):
        calls.append(args[1:3])
        return original_scan(*args, **kwargs)

    monkeypatch.setattr(_receiver, "scan_receiver", tracked)
    cached = analyze_session(session, cache_dir=cache)
    assert not calls
    assert cached.overview.iloc[0]["cached_receiver_recordings"] == 2
    pd.testing.assert_frame_equal(initial.receiver_attempts, cached.receiver_attempts)
    for name in ("frames.parquet", "attempts.parquet", "phases.parquet"):
        path = session.path / name
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        changed = analyze_session(session, cache_dir=cache)
        assert changed.overview.iloc[0]["cached_receiver_recordings"] == 0
        assert len(calls) == 2
        calls.clear()
    analyze_session(session, cache_dir=cache, refresh=True)
    assert len(calls) == 2


def test_analyze_session_cache_reconstructs_changed_events(session, tmp_path):
    cache = tmp_path / "cache"
    analyze_session(session, cache_dir=cache)
    root = _root(session)
    events = [dict(event) for event in _EVENTS]
    events[2]["monotonic_ns"] = 2_200_000_000
    (root / "events.jsonl").write_text("\n".join(map(json.dumps, events)))
    changed = analyze_session(_load(root), cache_dir=cache)
    assert changed.overview.iloc[0]["cached_receiver_recordings"] == 0
    assert changed.phase_packet_counts.query("receiver_id == 'rx-1'")[
        "sensing_link_csi_rows"
    ].tolist() == [2, 0, 1]


def test_analyze_session_partial_invalid_attempt_does_not_require_confirmation(
    tmp_path,
):
    attempt = {
        **_ATTEMPT,
        "status": "invalid",
        "action_confirmed": False,
        "ended_monotonic_ns": 2_400_000_000,
    }
    root = _build(tmp_path, attempts=[attempt], events=_EVENTS[:3])
    report = analyze_session(_load(root))
    assert report.phase_issues.empty
    assert report.phase_attempts.iloc[0]["phase_sequence"] == "countdown → action"


def test_analyze_session_rejects_cache_in_raw_data(session):
    with pytest.raises(ValueError, match="outside raw"):
        analyze_session(session, cache_dir=_root(session).parent.parent / "cache")


def test_analyze_session_reports_receivers_without_frames(tmp_path):
    session = _load(_build(tmp_path, frames=[]))
    report = analyze_session(session)
    receivers = report.receivers.set_index("receiver_id")
    assert receivers["attempts_without_frames"].tolist() == [1, 1]
    assert receivers["raw_csi_rows"].tolist() == [0, 0]
    assert not report.receiver_attempts["has_frames"].any()
    assert report.receiver_issues["receiver_id"].tolist() == ["rx-1", "rx-2"]
    assert report.receiver_attempts["sensing_link_rows"].tolist() == [0, 0]


def test_analyze_session_flags_unsupported_payload_layouts(tmp_path):
    frames = _frames()
    frames[0]["payload"] = bytes([0, 20] * 3)  # no known layout has three pairs
    session = _load(_build(tmp_path, frames=frames))
    report = analyze_session(session)
    receiver = report.receivers.set_index("receiver_id").loc["rx-1"]
    assert receiver["phase_mask_unsupported_rows"] == 1
    assert receiver["phase_mask_supported_rows"] == 2
    assert "rx-1" in report.receiver_issues["receiver_id"].tolist()


def test_phase_counts_treat_odd_or_empty_payloads_as_unreadable():
    table = pa.table(
        {
            "csi": pa.array([b"\x00\x14\x07", b"", b"\x00\x14" * 3], pa.binary()),
            "stbc": pa.array([0, 0, 0], pa.uint8()),
            "first_word_invalid": pa.array([False, False, False]),
        }
    )
    counts = _receiver._phase_counts(table)
    assert counts["phase_mask_unreadable_rows"] == 2
    assert counts["phase_mask_unsupported_rows"] == 1
    assert counts["phase_mask_supported_rows"] == 0


def test_analyze_session_counts_sequence_disorder_in_delivery_order(tmp_path):
    frames = _frames()
    frames[1]["sequence"], frames[2]["sequence"] = 13, 11  # delivered out of order
    report = analyze_session(_load(_build(tmp_path, frames=frames)))
    row = report.receiver_attempts.query("receiver_id == 'rx-1'").iloc[0]
    assert row["sequence_out_of_order"] == 1
    assert "rx-1" in report.receiver_issues["receiver_id"].tolist()


def test_analyze_latest_session_uses_manifest_start_time(session, tmp_path):
    root = _root(session)
    earlier = root.parent / "zzzz-earlier"
    shutil.copytree(root, earlier)
    path = earlier / "session.json"
    manifest = json.loads(path.read_text())
    manifest["started_at_utc"] = "2026-01-01T00:00:00+00:00"
    _json(path, manifest)
    report = analyze_latest_session(root.parent, tmp_path / "frames")
    assert report.session_dir == root


def test_analyze_session_handles_no_attempts(tmp_path):
    root = _build(tmp_path)
    shutil.rmtree(root / "trials")
    report = analyze_session(_load(root))
    assert report.attempts.empty
    assert report.receiver_issues.empty
    assert report.phase_issues.empty
    assert report.trial_coverage.iloc[0]["planned_trials_never_started"] == 1


def test_analyze_session_ignores_corrupt_cache(session, tmp_path):
    cache = tmp_path / "cache"
    analyze_session(session, cache_dir=cache)
    for path in cache.glob("*.json"):
        path.write_text("broken")
    repaired = analyze_session(session, cache_dir=cache)
    assert repaired.overview.iloc[0]["cached_receiver_recordings"] == 0


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
