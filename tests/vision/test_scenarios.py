from __future__ import annotations

from fall_detection.vision.rules import (
    BoundingBox,
    DetectionOutput,
    DetectorState,
    Keypoint,
    PoseObservation,
)
from fall_detection.vision.scenarios import (
    ActivityObservation,
    ActivityRecognizer,
    MotionState,
    PostureState,
    ScenarioCompletionConfig,
    ScenarioCompletionRecognizer,
    ScenarioRecognitionStatus,
)


def pose(
    timestamp: float,
    posture: str,
    *,
    x_shift: float = 0.0,
    ankle_shift: float = 0.0,
) -> PoseObservation:
    """Build a deterministic upright or seated COCO-style pose."""

    points = [Keypoint(0.5, 0.5, 0.0) for _ in range(17)]
    points[5] = Keypoint(0.45 + x_shift, 0.25, 0.95)
    points[6] = Keypoint(0.55 + x_shift, 0.25, 0.95)
    points[11] = Keypoint(0.47 + x_shift, 0.50, 0.95)
    points[12] = Keypoint(0.53 + x_shift, 0.50, 0.95)
    if posture == "standing":
        points[13] = Keypoint(0.46 + x_shift, 0.75, 0.95)
        points[14] = Keypoint(0.54 + x_shift, 0.75, 0.95)
        points[15] = Keypoint(0.46 + x_shift + ankle_shift, 0.95, 0.95)
        points[16] = Keypoint(0.54 + x_shift - ankle_shift, 0.95, 0.95)
    else:
        points[13] = Keypoint(0.65 + x_shift, 0.75, 0.95)
        points[14] = Keypoint(0.75 + x_shift, 0.75, 0.95)
        points[15] = Keypoint(0.80 + x_shift + ankle_shift, 0.75, 0.95)
        points[16] = Keypoint(0.90 + x_shift - ankle_shift, 0.75, 0.95)
    return PoseObservation(
        timestamp,
        tuple(points),
        BoundingBox(0.25 + x_shift, 0.1, 0.75 + x_shift, 0.98),
    )


def observation(
    timestamp: float,
    posture: PostureState,
    motion: MotionState = MotionState.STATIONARY,
    reliable: bool = True,
) -> ActivityObservation:
    return ActivityObservation(timestamp, posture, motion, reliable)


def test_activity_recognizer_classifies_standing_and_seated_pose():
    recognizer = ActivityRecognizer()

    standing = recognizer.update(
        pose(0.0, "standing"), DetectionOutput(DetectorState.MONITORING)
    )
    seated = recognizer.update(
        pose(0.2, "seated"), DetectionOutput(DetectorState.MONITORING)
    )

    assert standing.posture is PostureState.STANDING
    assert standing.reliable
    assert seated.posture is PostureState.SEATED


def test_activity_recognizer_detects_translation_with_leg_articulation():
    recognizer = ActivityRecognizer()
    outputs = [
        recognizer.update(
            pose(
                index * 0.2,
                "standing",
                x_shift=index * 0.1,
                ankle_shift=index * 0.04,
            ),
            DetectionOutput(DetectorState.MONITORING),
        )
        for index in range(4)
    ]

    assert outputs[0].motion is MotionState.STATIONARY
    assert outputs[-1].motion is MotionState.WALKING


def test_activity_recognizer_does_not_call_stationary_sway_walking():
    recognizer = ActivityRecognizer()
    outputs = [
        recognizer.update(
            pose(index * 0.2, "standing", x_shift=(index % 2) * 0.01),
            DetectionOutput(DetectorState.MONITORING),
        )
        for index in range(5)
    ]

    assert all(output.motion is not MotionState.WALKING for output in outputs)


def test_scenario_recognizer_requires_the_source_before_target():
    config = ScenarioCompletionConfig(posture_hold_seconds=0.2)
    recognizer = ScenarioCompletionRecognizer("sit_to_stand", config)

    recognizer.update(
        observation(0.0, PostureState.STANDING), action_active=True
    )
    result = recognizer.update(
        observation(0.2, PostureState.STANDING), action_active=True
    )

    assert result.status is ScenarioRecognitionStatus.WAITING_FOR_SOURCE


def test_all_supported_scenarios_complete_the_expected_sequence():
    config = ScenarioCompletionConfig(
        posture_hold_seconds=0.2,
        walking_hold_seconds=0.2,
    )
    sequences = {
        "walk_to_fall": (
            [(MotionState.WALKING, PostureState.STANDING)] * 2
            + [(MotionState.STATIONARY, PostureState.FALLEN)],
        ),
        "sit_to_fall": (
            [(MotionState.STATIONARY, PostureState.SEATED)] * 2
            + [(MotionState.STATIONARY, PostureState.FALLEN)],
        ),
        "stand_to_fall": (
            [(MotionState.STATIONARY, PostureState.STANDING)] * 2
            + [(MotionState.STATIONARY, PostureState.FALLEN)],
        ),
        "walk_to_sit": (
            [(MotionState.WALKING, PostureState.STANDING)] * 2
            + [(MotionState.STATIONARY, PostureState.SEATED)] * 2,
        ),
        "sit_to_walk": (
            [(MotionState.STATIONARY, PostureState.SEATED)] * 2
            + [(MotionState.WALKING, PostureState.STANDING)] * 2,
        ),
        "sit_to_stand": (
            [(MotionState.STATIONARY, PostureState.SEATED)] * 2
            + [(MotionState.STATIONARY, PostureState.STANDING)] * 2,
        ),
    }

    for label, (steps,) in sequences.items():
        recognizer = ScenarioCompletionRecognizer(label, config)
        result = None
        for index, (motion, posture) in enumerate(steps):
            result = recognizer.update(
                observation(index * 0.2, posture, motion),
                action_active=True,
            )
        assert result is not None
        assert result.status is ScenarioRecognitionStatus.COMPLETED, label
        assert result.observed_steps == tuple(
            {
                "walk_to_fall": ("walking", "fallen"),
                "sit_to_fall": ("seated", "fallen"),
                "stand_to_fall": ("standing", "fallen"),
                "walk_to_sit": ("walking", "seated"),
                "sit_to_walk": ("seated", "walking"),
                "sit_to_stand": ("seated", "standing"),
            }[label]
        )


def test_source_posture_can_be_confirmed_during_countdown():
    config = ScenarioCompletionConfig(posture_hold_seconds=0.2)
    recognizer = ScenarioCompletionRecognizer("sit_to_stand", config)

    recognizer.update(
        observation(0.0, PostureState.SEATED), action_active=False
    )
    waiting = recognizer.update(
        observation(0.2, PostureState.SEATED), action_active=False
    )
    completed = recognizer.update(
        observation(0.4, PostureState.STANDING), action_active=True
    )
    completed = recognizer.update(
        observation(0.7, PostureState.STANDING), action_active=True
    )

    assert waiting.status is ScenarioRecognitionStatus.WAITING_FOR_TARGET
    assert completed.status is ScenarioRecognitionStatus.COMPLETED


def test_timeout_distinguishes_missing_evidence_from_wrong_sequence():
    config = ScenarioCompletionConfig(
        minimum_reliable_frame_fraction=0.6,
    )
    wrong_sequence = ScenarioCompletionRecognizer("sit_to_stand", config)
    for index in range(5):
        wrong_sequence.update(
            observation(index * 0.2, PostureState.STANDING), action_active=True
        )
    assert (
        wrong_sequence.finalize_timeout().status
        is ScenarioRecognitionStatus.NOT_DETECTED
    )

    missing = ScenarioCompletionRecognizer("sit_to_stand", config)
    missing.update(observation(0.0, PostureState.SEATED, reliable=True), action_active=True)
    for index in range(1, 5):
        missing.update(
            observation(index * 0.2, PostureState.UNKNOWN, reliable=False),
            action_active=True,
        )
    assert missing.finalize_timeout().status is ScenarioRecognitionStatus.UNCERTAIN


def test_fallen_state_is_taken_from_the_existing_fall_detector():
    recognizer = ActivityRecognizer()
    result = recognizer.update(
        pose(0.0, "standing"), DetectionOutput(DetectorState.FALLEN)
    )

    assert result.posture is PostureState.FALLEN
