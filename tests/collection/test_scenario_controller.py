from __future__ import annotations

import json
from pathlib import Path

from fall_detection.collection.camera import CameraFrame
from fall_detection.collection.capture import SessionMetadata
from fall_detection.collection.controller import (
    HealthSnapshot,
    OperatorCommand,
    SessionController,
    SessionState,
)
from fall_detection.collection.protocol import protocol_from_mapping
from fall_detection.vision.scenarios import (
    ActivityObservation,
    MotionState,
    PostureState,
    ScenarioCompletionConfig,
    ScenarioRecognitionStatus,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def protocol(activity_label: str):
    return protocol_from_mapping(
        {
            "schema_version": 1,
            "protocol_id": "scenario-test",
            "title": "Scenario test",
            "defaults": {
                "countdown_seconds": 1,
                "action_seconds": 5,
                "recovery_seconds": 1,
            },
            "blocks": [
                {
                    "id": "block",
                    "title": "Block",
                    "scenarios": [
                        {
                            "id": "scenario",
                            "activity_label": activity_label,
                            "title": "Scenario",
                            "instruction": "Perform the scenario",
                        }
                    ],
                }
            ],
        }
    )


def health() -> HealthSnapshot:
    return HealthSnapshot(
        radio_live=True,
        camera_live=True,
        storage_ready=True,
        clock_sync_ready=True,
    )


def activity_frame(activity: ActivityObservation) -> CameraFrame:
    return CameraFrame(
        timestamp_ns=int(activity.timestamp_s * 1_000_000_000),
        frame=None,
        detector_state="monitoring",
        proposal={},
        pose=None,
        activity=activity,
    )


def make_controller(
    tmp_path: Path,
    clock: FakeClock,
    activity_label: str,
    *,
    auto_finish: bool = True,
) -> SessionController:
    controller = SessionController(
        protocol(activity_label),
        tmp_path,
        clock=clock,
        monotonic_ns=lambda: int(clock.value * 1_000_000_000),
        session_id_factory=lambda: "session",
        scenario_config=ScenarioCompletionConfig(
            posture_hold_seconds=0.2,
            walking_hold_seconds=0.2,
        ),
        scenario_auto_finish=auto_finish,
    )
    controller.start_session(SessionMetadata("participant-01"))
    controller.update_health(health())
    controller.dispatch(OperatorCommand.START_TRIAL)
    clock.advance(1)
    controller.tick()
    return controller


def walking(timestamp: float) -> ActivityObservation:
    return ActivityObservation(
        timestamp, PostureState.STANDING, MotionState.WALKING, True
    )


def seated(timestamp: float) -> ActivityObservation:
    return ActivityObservation(
        timestamp, PostureState.SEATED, MotionState.STATIONARY, True
    )


def standing(timestamp: float) -> ActivityObservation:
    return ActivityObservation(
        timestamp, PostureState.STANDING, MotionState.STATIONARY, True
    )


def test_completed_transition_enters_recovery_and_persists_recognition(tmp_path: Path):
    clock = FakeClock()
    controller = make_controller(tmp_path, clock, "walk_to_sit")

    controller.write_camera_frame(activity_frame(walking(0.0)))
    controller.write_camera_frame(activity_frame(walking(0.2)))
    controller.write_camera_frame(activity_frame(seated(0.4)))
    controller.write_camera_frame(activity_frame(seated(0.7)))

    snapshot = controller.tick()
    assert snapshot.state is SessionState.RECOVERY
    assert snapshot.scenario_recognition is not None
    assert (
        snapshot.scenario_recognition.status
        is ScenarioRecognitionStatus.COMPLETED
    )

    clock.advance(1)
    assert controller.tick().state is SessionState.REVIEW
    attempt = tmp_path / "session" / "trials" / "001_scenario" / "attempt_01"
    payload = json.loads((attempt / "attempt.json").read_text())
    assert payload["scenario_recognition"]["status"] == "completed"
    assert payload["scenario_recognition"]["source_confirmed_at_s"] is not None
    assert payload["scenario_recognition"]["completed_at_s"] is not None
    assert "activity" in (attempt / "camera_frames.csv").read_text().splitlines()[0]

    # Recognition never accepts the attempt on the operator's behalf.
    assert controller.dispatch(OperatorCommand.ACCEPT).state is SessionState.COMPLETE


def test_timeout_is_flagged_but_can_still_be_accepted(tmp_path: Path):
    clock = FakeClock()
    controller = make_controller(tmp_path, clock, "sit_to_stand")

    clock.advance(5)
    recovery = controller.tick()
    assert recovery.state is SessionState.RECOVERY
    assert recovery.scenario_recognition is not None
    assert (
        recovery.scenario_recognition.status
        is ScenarioRecognitionStatus.UNCERTAIN
    )
    clock.advance(1)
    review = controller.tick()
    assert review.state is SessionState.REVIEW
    assert "pose validation warning" in review.message
    assert controller.dispatch(OperatorCommand.ACCEPT).state is SessionState.COMPLETE


def test_retry_resets_scenario_recognizer_for_a_new_attempt(tmp_path: Path):
    clock = FakeClock()
    controller = make_controller(tmp_path, clock, "sit_to_stand")
    clock.advance(5)
    controller.tick()
    clock.advance(1)
    controller.tick()

    retry = controller.dispatch(OperatorCommand.RETRY)
    assert retry.state is SessionState.READY
    assert retry.scenario_recognition is None

    controller.update_health(health())
    started = controller.dispatch(OperatorCommand.START_TRIAL)
    assert started.scenario_recognition is not None
    assert (
        started.scenario_recognition.status
        is ScenarioRecognitionStatus.WAITING_FOR_SOURCE
    )


def test_unsupported_activity_keeps_the_existing_timed_workflow(tmp_path: Path):
    clock = FakeClock()
    controller = make_controller(tmp_path, clock, "other_activity")

    assert controller.tick().state is SessionState.ACTION
    clock.advance(5)
    recovery = controller.tick()
    assert recovery.state is SessionState.RECOVERY
    assert recovery.scenario_recognition is not None
    assert (
        recovery.scenario_recognition.status
        is ScenarioRecognitionStatus.UNSUPPORTED
    )


def test_disabling_auto_finish_keeps_action_timer_authoritative(tmp_path: Path):
    clock = FakeClock()
    controller = make_controller(
        tmp_path,
        clock,
        "sit_to_stand",
        auto_finish=False,
    )

    controller.write_camera_frame(activity_frame(seated(0.0)))
    controller.write_camera_frame(activity_frame(seated(0.2)))
    controller.write_camera_frame(activity_frame(standing(0.4)))
    controller.write_camera_frame(activity_frame(standing(0.7)))
    assert controller.state is SessionState.ACTION
    snapshot = controller.tick()
    assert snapshot.scenario_recognition is not None
    assert (
        snapshot.scenario_recognition.status
        is ScenarioRecognitionStatus.COMPLETED
    )

    clock.advance(5)
    assert controller.tick().state is SessionState.RECOVERY
