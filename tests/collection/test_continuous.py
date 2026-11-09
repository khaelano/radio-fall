import json

from fall_detection.collection.capture import SessionMetadata
from fall_detection.collection.continuous import ContinuousController, continuous_protocol
from fall_detection.collection.controller import HealthSnapshot, OperatorCommand, SessionState


def test_segments_recover_after_interruption_and_keep_gap_journal(tmp_path):
    now = [0.0]
    controller = ContinuousController(
        continuous_protocol(10, 2), tmp_path, clock=lambda: now[0],
        monotonic_ns=lambda: int(now[0] * 1e9), session_id_factory=lambda: "test", environment={"receiver_ids": {"00:11:22:33:44:55": "rx-1"}},
    )
    controller.start_session(SessionMetadata("participant"))
    ready = HealthSnapshot(radio_live=True, storage_ready=True, clock_sync_ready=True)
    controller.update_health(ready)
    assert controller.tick().state is SessionState.ACTION
    now[0] = 10
    assert controller.tick().state is SessionState.ACTION
    first = tmp_path / "test/trials/001_activity/attempt_01/attempt.json"
    metadata = json.loads(first.read_text())
    assert metadata["status"] == "accepted"
    assert metadata["activity_label"] == "non_fall"
    now[0] = 13
    controller.interrupt_radio("link lost")
    assert controller.tick().state is SessionState.READY
    now[0] = 20
    controller.update_health(ready)
    assert controller.tick().state is SessionState.ACTION
    now[0] = 30
    assert controller.tick().state is SessionState.COMPLETE
    partial = tmp_path / "test/trials/002_activity/attempt_01/attempt.json"
    assert json.loads(partial.read_text())["status"] == "invalid"
    assert json.loads((partial.parent.parent / "attempt_02/attempt.json").read_text())["status"] == "accepted"
    events = [json.loads(line) for line in (tmp_path / "test/events.jsonl").read_text().splitlines()]
    gaps = [e for e in events if e["kind"] == "continuous_gap_ended"]
    assert gaps[-1]["monotonic_ns"] == 20_000_000_000
    assert gaps[-1]["started_monotonic_ns"] == 13_000_000_000


def test_stop_preserves_partial_segment_as_incomplete(tmp_path):
    controller = ContinuousController(continuous_protocol(10, 2), tmp_path,
                                      session_id_factory=lambda: "test", environment={"receiver_ids": {"00:11:22:33:44:55": "rx-1"}})
    controller.start_session(SessionMetadata("participant"))
    controller.update_health(HealthSnapshot(radio_live=True, storage_ready=True, clock_sync_ready=True))
    controller.tick()
    controller.dispatch(OperatorCommand.END_SESSION)
    path = tmp_path / "test/trials/001_activity/attempt_01/attempt.json"
    assert json.loads(path.read_text())["status"] == "incomplete"


def test_resume_keeps_completed_segment_and_retries_partial(tmp_path):
    now = [0.0]
    env = {"receiver_ids": {"00:11:22:33:44:55": "rx-1"}}
    protocol = continuous_protocol(10, 3)
    options = dict(clock=lambda: now[0], monotonic_ns=lambda: int(now[0] * 1e9),
                   environment=env)
    controller = ContinuousController(protocol, tmp_path, session_id_factory=lambda: "test", **options)
    ready = HealthSnapshot(radio_live=True, storage_ready=True, clock_sync_ready=True)
    controller.start_session(SessionMetadata("participant"))
    controller.update_health(ready)
    controller.tick()
    now[0] = 10
    controller.tick()
    first = tmp_path / "test/trials/001_activity/attempt_01/attempt.json"
    original = first.read_bytes()
    controller.dispatch(OperatorCommand.END_SESSION)
    resumed = ContinuousController(protocol, tmp_path, **options)
    resumed.resume_session(tmp_path / "test")
    resumed.update_health(ready)
    resumed.tick()
    assert first.read_bytes() == original
    assert (tmp_path / "test/trials/002_activity/attempt_02/attempt.json").exists()
    resumed.dispatch(OperatorCommand.END_SESSION)
