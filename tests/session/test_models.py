from __future__ import annotations

import json
from pathlib import Path

import pytest
from inspector_sessions import FrameSpec, attempt_origin

from fall_detection.session import (
    SessionReadError,
    load_session,
    scan_sessions,
    session_frames_directory,
)


def test_load_session_groups_attempts_by_trial(session_factory):
    root = session_factory(attempts=((1, 1, "invalid"), (1, 2, "accepted")))

    session = load_session(root, resolve_receivers=True)

    assert len(session.trials) == 2
    assert len(session.trials[0].attempts) == 2
    assert session.trials[1].attempts == ()
    assert session.attempts[0].receiver_ids == ("rx-1",)
    assert session.attempts[1].receiver_ids == ("rx-1",)
    assert session.labels == ("walk",)
    assert session.editable


def test_load_session_rejects_legacy_artifact_schema(session_factory):
    root = session_factory()
    manifest = json.loads((root / "session.json").read_text(encoding="utf-8"))
    manifest.pop("artifact_schema_version")
    (root / "session.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SessionReadError, match="unsupported artifact schema"):
        load_session(root)


def test_load_session_marks_open_or_recording_bundle_active(session_factory):
    open_root = session_factory("open", status="open")
    recording_root = session_factory("recording", attempts=((1, 1, "recording"),))

    assert load_session(open_root).active
    assert load_session(recording_root).active


def test_load_session_keeps_damaged_attempt_as_warning(session_factory):
    root = session_factory(attempts=((1, 1, "accepted"),))
    manifest = next(root.glob("trials/*/attempt_*/attempt.json"))
    manifest.write_text("{bad", encoding="utf-8")

    session = load_session(root, resolve_receivers=True)

    assert len(session.attempts) == 1
    assert session.attempts[0].status == "unknown"
    assert any("invalid JSON" in warning for warning in session.warnings)
    assert any("frame tables unavailable" in warning for warning in session.warnings)


def test_scan_sessions_supports_individual_path_and_ignores_unrelated_children(
    session_factory, tmp_path: Path
):
    root = session_factory()
    sessions_dir = root.parent
    (sessions_dir / "unrelated").mkdir()

    assert scan_sessions(root)[0].session_id == "session-1"
    assert [session.session_id for session in scan_sessions(sessions_dir)] == [
        "session-1"
    ]


def test_receivers_come_from_frames_in_each_attempt_window(session_factory):
    origin = attempt_origin(0)
    root = session_factory(
        attempts=((1, 1, "accepted"), (1, 2, "accepted")),
        frames=(
            FrameSpec(1, origin + 100_000_000, "rx-1"),
            FrameSpec(2, origin + 200_000_000, "rx-2"),
            FrameSpec(3, attempt_origin(1) + 100_000_000, "rx-2"),
        ),
    )

    session = load_session(root, resolve_receivers=True)

    assert session.attempts[0].receiver_ids == ("rx-1", "rx-2")
    assert session.attempts[1].receiver_ids == ("rx-2",)
    assert session.trials[0].attempts == session.attempts
    assert session.receivers_resolved


def test_directory_scan_lists_sessions_without_converting_them(session_factory):
    root = session_factory(attempts=((1, 1, "accepted"),))
    frames_path = load_session(root).attempts[0].frames_path

    listed = scan_sessions(root.parent)[0]

    assert not listed.receivers_resolved
    assert listed.attempts[0].receiver_ids == ()
    assert not frames_path.exists()
    resolved = listed.with_receivers()
    assert resolved.receivers_resolved
    assert resolved.attempts[0].receiver_ids == ("rx-1",)
    assert resolved.trials[0].attempts == resolved.attempts
    assert frames_path.is_dir()
    assert resolved.with_receivers() is resolved


def test_session_without_journals_loads_without_receivers(session_factory):
    root = session_factory(attempts=((1, 1, "accepted"),))
    for journal in root.glob("transport/**/*"):
        if journal.is_file():
            journal.unlink()

    session = load_session(root, resolve_receivers=True)

    assert len(session.attempts) == 1
    assert session.attempts[0].receiver_ids == ()


def test_frames_directory_rule(tmp_path: Path):
    standard = tmp_path / "data" / "raw" / "sessions" / "one"
    other = tmp_path / "elsewhere" / "one"

    assert session_frames_directory(standard, "one") == (
        tmp_path / "data" / "interim" / "frames" / "one"
    )
    assert session_frames_directory(other, "one") == (
        tmp_path / "interim" / "frames" / "one"
    )
    with pytest.raises(ValueError):
        session_frames_directory(standard, "../one")


def test_invalid_individual_session_raises(tmp_path: Path):
    root = tmp_path / "broken"
    root.mkdir()
    (root / "session.json").write_text("[]", encoding="utf-8")

    with pytest.raises(SessionReadError, match="must contain an object"):
        load_session(root)
