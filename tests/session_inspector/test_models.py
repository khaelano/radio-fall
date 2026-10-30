from __future__ import annotations

import json
from pathlib import Path

import pytest

from fall_detection.session_inspector.models import (
    SessionReadError,
    load_session,
    scan_sessions,
)


def test_load_session_groups_attempts_by_trial(session_factory):
    root = session_factory(attempts=((1, 1, "invalid"), (1, 2, "accepted")))

    session = load_session(root)

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

    session = load_session(root)

    assert len(session.attempts) == 1
    assert session.attempts[0].status == "unknown"
    assert any("invalid JSON" in warning for warning in session.warnings)


def test_scan_sessions_supports_individual_path_and_ignores_unrelated_children(
    session_factory, tmp_path: Path
):
    root = session_factory()
    (tmp_path / "unrelated").mkdir()

    assert scan_sessions(root)[0].session_id == "session-1"
    assert [session.session_id for session in scan_sessions(tmp_path)] == ["session-1"]


def test_invalid_individual_session_raises(tmp_path: Path):
    root = tmp_path / "broken"
    root.mkdir()
    (root / "session.json").write_text("[]", encoding="utf-8")

    with pytest.raises(SessionReadError, match="must contain an object"):
        load_session(root)
