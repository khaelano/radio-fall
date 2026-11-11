from __future__ import annotations

from pathlib import Path
import json

import pytest

from fall_detection.collection.capture import SessionMetadata
from fall_detection.collection.controller import (
    HealthSnapshot,
    OperatorCommand,
    SessionController,
    SessionState,
)
from fall_detection.collection.protocol import protocol_from_mapping
from fall_detection.radio.acquisition.telemetry import (
    BackhaulTelemetrySnapshot,
    GatewayTelemetry,
    TransmitterTelemetry,
)
from fall_detection.radio.acquisition.wire import ReceiverStats


def protocol():
    return {
        "schema_version": 1,
        "protocol_id": "test",
        "title": "Test protocol",
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
                        "id": "one",
                        "activity_label": "walk",
                        "title": "Walk",
                        "instruction": "Walk forward",
                    }
                ],
            }
        ],
    }


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def ready_health() -> HealthSnapshot:
    return HealthSnapshot(
        radio_live=True,
        storage_ready=True,
        clock_sync_ready=True,
    )


def make_controller(
    tmp_path: Path, clock: FakeClock, *, video_recorder=None
) -> SessionController:
    return SessionController(
        protocol_from_mapping(protocol()),
        tmp_path,
        clock=clock,
        monotonic_ns=lambda: int(clock.value * 1_000_000_000),
        session_id_factory=lambda: "session",
        video_recorder=video_recorder,
        environment={"receiver_ids": {"00:11:22:33:44:55": "rx-1"}},
    )


def start_ready(controller: SessionController) -> None:
    controller.start_session(SessionMetadata("participant-01"))
    controller.update_health(ready_health())


def test_radio_interruption_invalidates_attempt_before_display_refresh(tmp_path):
    controller = make_controller(tmp_path, FakeClock())
    start_ready(controller)
    controller.dispatch(OperatorCommand.START_TRIAL)

    interrupted = controller.interrupt_radio("transmitter restarted")

    assert interrupted.state is SessionState.REVIEW
    assert interrupted.attempt_status == "invalid"
    assert not interrupted.health.radio_live
    assert not interrupted.health.clock_sync_ready
    recovered = controller.update_health(ready_health())
    assert recovered.attempt_status == "invalid"
    with pytest.raises(RuntimeError, match="invalid attempt"):
        controller.dispatch(OperatorCommand.ACCEPT)


def test_controller_runs_timed_trial_and_writes_bundle(tmp_path: Path):
    clock = FakeClock()
    controller = make_controller(tmp_path, clock)
    start_ready(controller)

    snapshot = controller.dispatch(OperatorCommand.START_TRIAL)
    assert snapshot.state is SessionState.COUNTDOWN
    assert snapshot.trial.ordinal == 1

    clock.advance(1)
    assert controller.tick().state is SessionState.ACTION
    clock.advance(2)
    assert controller.tick().state is SessionState.RECOVERY
    clock.advance(1)
    assert controller.tick().state is SessionState.REVIEW

    controller.dispatch(OperatorCommand.ACCEPT)
    assert controller.state is SessionState.COMPLETE
    attempt_dir = tmp_path / "session" / "trials" / "001_one" / "attempt_01"
    assert (attempt_dir / "attempt.json").exists()
    assert (attempt_dir / "receivers" / "rx-1" / "csi.csv").exists()
    session_manifest = json.loads((tmp_path / "session" / "session.json").read_text())
    attempt_manifest = json.loads((attempt_dir / "attempt.json").read_text())
    assert session_manifest["artifact_schema_version"] == 2
    assert attempt_manifest["artifact_schema_version"] == 2
    assert attempt_manifest["status"] == "accepted"


def test_controller_requires_all_inputs_before_start(tmp_path: Path):
    clock = FakeClock()
    controller = make_controller(tmp_path, clock)
    controller.start_session(SessionMetadata("participant-01"))

    with pytest.raises(RuntimeError, match="health"):
        controller.dispatch(OperatorCommand.START_TRIAL)


def test_lost_input_marks_attempt_invalid_and_retry_gets_new_number(tmp_path: Path):
    clock = FakeClock()
    controller = make_controller(tmp_path, clock)
    start_ready(controller)
    controller.dispatch(OperatorCommand.START_TRIAL)

    controller.update_health(
        HealthSnapshot(
            radio_live=False,
            radio_detail="radio disconnected",
        )
    )
    assert controller.state is SessionState.REVIEW
    attempt = (
        tmp_path / "session" / "trials" / "001_one" / "attempt_01" / "attempt.json"
    )
    assert '"status": "invalid"' in attempt.read_text()

    controller.dispatch(OperatorCommand.RETRY)
    controller.update_health(ready_health())
    controller.dispatch(OperatorCommand.START_TRIAL)
    assert controller.state is SessionState.COUNTDOWN
    assert (
        tmp_path / "session" / "trials" / "001_one" / "attempt_02" / "attempt.json"
    ).exists()


def test_invalid_attempt_cannot_be_accepted(tmp_path: Path):
    clock = FakeClock()
    controller = make_controller(tmp_path, clock)
    start_ready(controller)
    controller.dispatch(OperatorCommand.START_TRIAL)
    controller.update_health(HealthSnapshot(radio_live=False))

    with pytest.raises(RuntimeError, match="cannot be accepted"):
        controller.dispatch(OperatorCommand.ACCEPT)


def test_subscribers_receive_the_same_immutable_snapshot(tmp_path: Path):
    clock = FakeClock()
    controller = make_controller(tmp_path, clock)
    first = []
    second = []
    controller.subscribe(first.append)
    controller.subscribe(second.append)
    controller.start_session(SessionMetadata("participant-01"))

    assert first[-1] == second[-1]
    assert first[-1].state is SessionState.READY


def test_attempt_persists_boot_aware_radio_telemetry_delta(tmp_path: Path):
    clock = FakeClock()

    def telemetry(timestamp: int, records: int, boot_id: int = 7):
        return BackhaulTelemetrySnapshot(
            captured_monotonic_ns=timestamp,
            records=records,
            batches=records,
            host_missing_sequences=0,
            transport_missing=0,
            transport_reordered=0,
            batch_missing=0,
            batch_reordered=0,
            malformed=0,
            foreign=0,
            receiver_restarts=0,
            serial_frames=records,
            receiver_boot_id=boot_id,
            receiver_stats=ReceiverStats(
                records, 0, 0, 0, 0, 0, records, records, records, 0
            ),
            transmitter_stats=TransmitterTelemetry(1000, records, 0, records, 0),
            gateway_stats=GatewayTelemetry(1000, records, 0, 0, records, 0),
        )

    snapshots = iter((telemetry(0, 0), telemetry(5_000_000_000, 5)))
    controller = SessionController(
        protocol_from_mapping(protocol()),
        tmp_path,
        clock=clock,
        monotonic_ns=lambda: int(clock.value * 1_000_000_000),
        session_id_factory=lambda: "session",
        telemetry_provider=lambda: next(snapshots),
        environment={"receiver_ids": {"00:11:22:33:44:55": "rx-1"}},
    )
    start_ready(controller)
    controller.dispatch(OperatorCommand.START_TRIAL)
    clock.advance(1)
    controller.tick()
    clock.advance(2)
    controller.tick()
    clock.advance(1)
    controller.tick()
    controller.dispatch(OperatorCommand.ACCEPT)

    payload = json.loads(
        (
            tmp_path / "session" / "trials" / "001_one" / "attempt_01" / "attempt.json"
        ).read_text()
    )
    assert payload["radio_telemetry_delta"]["complete"]
    assert payload["radio_telemetry_delta"]["values"]["records"] == 5


def test_ble_delayed_records_route_by_capture_time_across_attempts(tmp_path: Path):
    from dataclasses import replace
    from fall_detection.radio.acquisition.protocol import CsiRecord

    clock = FakeClock()
    controller = SessionController(
        protocol_from_mapping(protocol()),
        tmp_path,
        clock=clock,
        monotonic_ns=lambda: int(clock.value * 1_000_000_000),
        session_id_factory=lambda: "ble-session",
        environment={
            "receiver_ids": {"00:11:22:33:44:55": "rx-1"},
            "transport": "ble",
            "ble_transport": {"drain_ms": 300},
        },
    )
    start_ready(controller)
    controller.dispatch(OperatorCommand.START_TRIAL)
    clock.advance(1)
    controller.dispatch(OperatorCommand.ABORT)
    controller.dispatch(OperatorCommand.RETRY)
    clock.advance(0.01)
    controller.dispatch(OperatorCommand.START_TRIAL)
    record = CsiRecord(
        1,
        "00:11:22:33:44:66",
        -40,
        -95,
        100,
        (1 + 2j,),
        receiver_mac="00:11:22:33:44:55",
        csi_length=2,
        run_id=123,
        transmitter_boot_id=11,
        receiver_boot_id=21,
        capture_host_monotonic_ns=900_000_000,
    )
    controller.write_radio(record, 1_050_000_000)
    controller.write_radio(
        replace(record, sequence=2, capture_host_monotonic_ns=1_020_000_000),
        1_060_000_000,
    )
    # Alignment failures and arrivals beyond the previous attempt's drain
    # deadline cannot become fresh observations in the new attempt.
    controller.write_radio(
        replace(record, sequence=3, capture_host_monotonic_ns=None), 1_070_000_000
    )
    clock.advance(0.4)
    controller.tick()
    controller.write_radio(replace(record, sequence=4), 1_410_000_000)
    controller.dispatch(OperatorCommand.ABORT)
    controller.flush_radio()
    root = controller.session_root / "trials" / "001_one"
    first = (
        (root / "attempt_01" / "receivers" / "rx-1" / "csi.csv")
        .read_text()
        .splitlines()
    )
    second = (
        (root / "attempt_02" / "receivers" / "rx-1" / "csi.csv")
        .read_text()
        .splitlines()
    )
    assert len(first) == 2 and first[1].startswith("CSI_DATA,1,")
    assert len(second) == 2 and second[1].startswith("CSI_DATA,2,")
    controller.dispatch(OperatorCommand.END_SESSION)


class FakeVideo:
    def __init__(self):
        self.starts, self.ends = [], []
        self.finished = None

    def begin_attempt(self, path, start_ns):
        self.starts.append((path, start_ns))
        return {
            "video_file": "camera.mp4",
            "frame_timing_file": "camera_frames.csv",
            "metadata_file": "video.json",
        }

    def end_attempt(self, path, end_ns):
        self.ends.append((path, end_ns))

    def result(self, path):
        return self.finished


def test_video_markers_match_csi_attempt_timeline_and_gate_acceptance(tmp_path):
    clock, video = FakeClock(), FakeVideo()
    controller = make_controller(tmp_path, clock, video_recorder=video)
    start_ready(controller)
    controller.dispatch(OperatorCommand.START_TRIAL)
    clock.advance(1)
    controller.tick()
    clock.advance(2)
    controller.tick()
    clock.advance(1)
    controller.tick()
    assert video.starts[0][1] == 0
    assert video.ends[0] == (video.starts[0][0], 4_000_000_000)
    assert controller.dispatch(OperatorCommand.ACCEPT).accept_pending
    video.finished = {"status": "complete", "frames": 120}
    clock.advance(5)  # Review does not extend capture/video boundaries.
    assert not controller.tick().accept_pending
    assert len(video.ends) == 1  # Review does not extend video or sensing capture.
    metadata = json.loads((video.starts[0][0] / "attempt.json").read_text())
    assert metadata["video"]["metadata_file"] == "video.json"
    assert metadata["ended_monotonic_ns"] == 4_000_000_000


def test_video_health_loss_invalidates_attempt_and_retry_gets_new_clip(tmp_path):
    clock, video = FakeClock(), FakeVideo()
    controller = make_controller(tmp_path, clock, video_recorder=video)
    start_ready(controller)
    controller.dispatch(OperatorCommand.START_TRIAL)
    clock.advance(0.5)
    controller.update_health(
        HealthSnapshot(
            radio_live=True, video_ready=False, video_detail="phone unplugged"
        )
    )
    assert controller.state is SessionState.REVIEW
    assert controller.tick().attempt_status == "invalid"
    with pytest.raises(RuntimeError, match="invalid"):
        controller.dispatch(OperatorCommand.ACCEPT)
    controller.dispatch(OperatorCommand.RETRY)
    with pytest.raises(RuntimeError, match="health"):
        controller.dispatch(OperatorCommand.START_TRIAL)
    controller.update_health(ready_health())
    controller.dispatch(OperatorCommand.START_TRIAL)
    assert video.starts[0][0] != video.starts[1][0]
    assert video.starts[1][0].name == "attempt_02"
    controller.dispatch(OperatorCommand.END_SESSION)
    assert len(video.ends) == 2


def test_video_finalization_failure_prevents_accepted_metadata(tmp_path):
    clock, video = FakeClock(), FakeVideo()
    controller = make_controller(tmp_path, clock, video_recorder=video)
    start_ready(controller)
    controller.dispatch(OperatorCommand.START_TRIAL)
    for seconds in (1, 2, 1):
        clock.advance(seconds)
        controller.tick()
    video.finished = {"status": "failed", "frames": 0}
    with pytest.raises(RuntimeError, match="video recording failed"):
        controller.dispatch(OperatorCommand.ACCEPT)
    metadata = json.loads((video.starts[0][0] / "attempt.json").read_text())
    assert metadata["status"] == "invalid"


@pytest.mark.parametrize(
    "command",
    [OperatorCommand.RETRY, OperatorCommand.SKIP, OperatorCommand.END_SESSION],
)
def test_queued_accept_can_be_cancelled_without_later_accepting(
    tmp_path, monkeypatch, command
):
    from fall_detection.collection.capture import TrialCapture

    clock = FakeClock()
    c = make_controller(tmp_path, clock)
    start_ready(c)
    c.dispatch(OperatorCommand.START_TRIAL)
    for seconds in (1, 2, 1):
        clock.advance(seconds)
        c.tick()
    capture = c._last_capture
    monkeypatch.setattr(TrialCapture, "writes_complete", property(lambda self: False))
    c._recording_io = object()  # Guard enabled; no flush or disk wait is available.
    assert c.dispatch(OperatorCommand.ACCEPT).accept_pending
    assert c.tick().accept_pending
    assert not c.dispatch(command).accept_pending
    monkeypatch.setattr(TrialCapture, "writes_complete", property(lambda self: True))
    assert not c.tick().accept_pending
    assert (
        json.loads((capture.path / "attempt.json").read_text())["status"] != "accepted"
    )
    c._recording_io = None
    c.dispatch(OperatorCommand.END_SESSION)


def test_queued_accept_reports_background_storage_failure(tmp_path, monkeypatch):
    from fall_detection.collection.capture import TrialCapture

    clock = FakeClock()
    c = make_controller(tmp_path, clock)
    start_ready(c)
    c.dispatch(OperatorCommand.START_TRIAL)
    for seconds in (1, 2, 1):
        clock.advance(seconds)
        c.tick()
    capture = c._last_capture
    monkeypatch.setattr(TrialCapture, "writes_complete", property(lambda self: False))
    c._recording_io = object()
    c.dispatch(OperatorCommand.ACCEPT)

    def failed(self):
        raise OSError("disk full")

    monkeypatch.setattr(TrialCapture, "writes_complete", property(failed))
    result = c.tick()
    assert not result.accept_pending
    assert result.attempt_status == "invalid"
    assert "disk full" in result.message
    assert (
        json.loads((capture.path / "attempt.json").read_text())["status"]
        == "pending_review"
    )
    c._recording_io = None
    c.dispatch(OperatorCommand.END_SESSION)
