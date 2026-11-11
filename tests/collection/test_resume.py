"""Resume explicit progress while preserving immutable attempt recordings."""

import json

import pytest

from fall_detection.collection.capture import SessionMetadata
from fall_detection.collection.controller import SessionController, OperatorCommand
from fall_detection.collection.protocol import protocol_from_mapping
from fall_detection.collection.resume import load_session_resume
from test_controller import FakeClock, protocol, ready_health

ENV = {"receiver_ids": {"00:11:22:33:44:55": "rx-1"}}


def test_resume_reads_and_appends_compressed_events(tmp_path):
    from fall_detection.radio.acquisition.recording_io import RecordingIO
    from fall_detection.storage.compressed import read_bytes

    clock = FakeClock()
    old = controller(tmp_path, clock)
    writer = RecordingIO(compressed=True)
    old._recording_io = writer
    old.start_session(SessionMetadata("p01"))
    old.dispatch(OperatorCommand.END_SESSION)
    old.flush_radio()
    writer.close()
    root = tmp_path / "session"
    assert not (root / "events.jsonl").exists()
    before = read_bytes(root / "events.jsonl")
    new = controller(tmp_path, clock)
    writer = RecordingIO(compressed=True)
    new._recording_io = writer
    new.resume_session(root)
    new.dispatch(OperatorCommand.END_SESSION)
    new.flush_radio()
    writer.close()
    assert read_bytes(root / "events.jsonl").startswith(before)
    load_session_resume(root)


def controller(tmp_path, clock):
    source = protocol()
    source["blocks"][0]["scenarios"][0]["repetitions"] = 3
    return SessionController(
        protocol_from_mapping(source),
        tmp_path,
        clock=clock,
        monotonic_ns=lambda: int(clock.value * 1e9),
        session_id_factory=lambda: "session",
        environment=ENV,
    )


def finish_attempt(c, clock):
    c.dispatch(OperatorCommand.START_TRIAL)
    for step in (1, 2, 1):
        clock.advance(step)
        c.tick()
    c.dispatch(OperatorCommand.ACCEPT)


def test_resume_retains_accepted_trial_and_uses_new_attempt_number(tmp_path):
    clock = FakeClock()
    old = controller(tmp_path, clock)
    old.start_session(SessionMetadata("p01"))
    old.update_health(ready_health())
    finish_attempt(old, clock)
    old.dispatch(OperatorCommand.START_TRIAL)
    old.interrupt_radio("gateway USB receive buffer age exceeded")
    old.dispatch(OperatorCommand.END_SESSION)
    old.flush_radio()
    root = tmp_path / "session"
    first = root / "trials/001_one/attempt_01"
    preserved = {p: p.read_bytes() for p in first.rglob("*") if p.is_file()}
    previous_events = (root / "events.jsonl").read_bytes()
    new = controller(tmp_path, clock)
    try:
        snapshot = new.resume_session(root)
        assert snapshot.trial.ordinal == 2
        assert snapshot.state.value == "ready"
        assert not snapshot.health.radio_live
        with pytest.raises(RuntimeError, match="health"):
            new.dispatch(OperatorCommand.START_TRIAL)
        new.update_health(ready_health())
        assert new.dispatch(OperatorCommand.START_TRIAL).attempt_number == 2
        assert (root / "trials/002_one/attempt_02/attempt.json").exists()
        assert all(p.read_bytes() == data for p, data in preserved.items())
        assert (root / "events.jsonl").read_bytes().startswith(previous_events)
    finally:
        new.dispatch(OperatorCommand.END_SESSION)
        new.flush_radio()


def test_resume_refuses_concurrent_writer(tmp_path):
    clock = FakeClock()
    old, new = controller(tmp_path, clock), controller(tmp_path, clock)
    old.start_session(SessionMetadata("p01"))
    try:
        with pytest.raises(ValueError, match="already open"):
            new.resume_session(tmp_path / "session")
    finally:
        old.dispatch(OperatorCommand.END_SESSION)


def test_resume_rejects_radio_identity_changes_without_mutating_files(tmp_path):
    clock = FakeClock()
    old = controller(tmp_path, clock)
    old.start_session(SessionMetadata("p01"))
    old.dispatch(OperatorCommand.END_SESSION)
    root = tmp_path / "session"
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    new = controller(tmp_path, clock)
    new.update_environment({"receiver_ids": {"00:11:22:33:44:66": "rx-1"}})
    with pytest.raises(ValueError, match="receiver_ids"):
        new.resume_session(root)
    assert all(p.read_bytes() == data for p, data in before.items())


def test_resume_invalidates_crash_orphan_without_reopening_its_streams(tmp_path):
    clock = FakeClock()
    old = controller(tmp_path, clock)
    old.start_session(SessionMetadata("p01"))
    old.update_health(ready_health())
    old.dispatch(OperatorCommand.START_TRIAL)
    old._capture.close_streams()
    old._store._event_file.close()  # Simulate process exit without final metadata.
    root = tmp_path / "session"
    attempt = root / "trials/001_one/attempt_01"
    original = (attempt / "attempt.json").read_bytes()
    raw = {p: p.read_bytes() for p in attempt.rglob("*.csv")}
    new = controller(tmp_path, clock)
    try:
        assert new.resume_session(root).trial.ordinal == 1
        assert json.loads((attempt / "attempt.json").read_text())["status"] == "invalid"
        assert (attempt / "attempt.before-resume.json").read_bytes() == original
        new.update_health(ready_health())
        new.dispatch(OperatorCommand.START_TRIAL)
        assert (root / "trials/001_one/attempt_02/attempt.json").exists()
        assert all(p.read_bytes() == data for p, data in raw.items())
    finally:
        new.dispatch(OperatorCommand.END_SESSION)
        new.flush_radio()


def test_resume_uses_saved_protocol_and_rejects_corruption(tmp_path):
    clock = FakeClock()
    old = controller(tmp_path, clock)
    old.start_session(SessionMetadata("p01"))
    old.dispatch(OperatorCommand.END_SESSION)
    root = tmp_path / "session"
    assert len(load_session_resume(root).protocol.trials) == 3
    p = root / "protocol.json"
    value = json.loads(p.read_text())
    value["title"] = "Changed"
    p.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="hash mismatch"):
        load_session_resume(root)


def test_accept_queues_while_saving_and_advances_without_another_click(tmp_path):
    from fall_detection.radio.acquisition.recording_io import RecordingIO

    clock = FakeClock()
    c = controller(tmp_path, clock)
    writer = RecordingIO(interval_s=60)
    c._recording_io = writer
    c._environment["transport"] = "espnow_gateway"
    c.start_session(SessionMetadata("p01"))
    c.update_health(ready_health())
    try:
        c.dispatch(OperatorCommand.START_TRIAL)
        for step in (1, 2, 1):
            clock.advance(step)
            c.tick()
        queued = c.dispatch(OperatorCommand.ACCEPT)
        assert queued.accept_pending
        assert queued.trial.ordinal == 1
        assert queued.attempt_status == "pending_review"
        clock.advance(2)
        c.tick()
        writer.flush()
        assert c.tick().trial.ordinal == 2
    finally:
        c.dispatch(OperatorCommand.END_SESSION)
        c.flush_radio()
        writer.close()


def test_resume_recovers_explicit_acceptance_before_resolution_event(tmp_path):
    clock = FakeClock()
    c = controller(tmp_path, clock)
    c.start_session(SessionMetadata("p01"))
    c.update_health(ready_health())
    finish_attempt(c, clock)
    c.dispatch(OperatorCommand.END_SESSION)
    path = tmp_path / "session/events.jsonl"
    path.write_text(
        "".join(
            line
            for line in path.read_text().splitlines(True)
            if json.loads(line)["kind"] != "trial_resolved"
        )
    )
    saved = load_session_resume(tmp_path / "session")
    assert saved.trial_index == 1 and saved.recovered_resolutions == (1,)
    resumed = controller(tmp_path, clock)
    try:
        assert resumed.resume_session(tmp_path / "session").trial.ordinal == 2
    finally:
        resumed.dispatch(OperatorCommand.END_SESSION)
