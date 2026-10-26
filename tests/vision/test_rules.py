from __future__ import annotations

from fall_detection.vision.rules import (
    BoundingBox,
    CocoKeypoint,
    DetectorState,
    DetectorTransition,
    FallRulesConfig,
    Keypoint,
    PoseObservation,
    RuleBasedFallDetector,
)


def observation(
    timestamp: float,
    hip_y: float,
    *,
    horizontal: bool = False,
    confidence: float = 0.95,
    track_id: int = 7,
) -> PoseObservation:
    points = [Keypoint(0.5, 0.5, 0.0) for _ in range(17)]
    if horizontal:
        points[CocoKeypoint.LEFT_SHOULDER] = Keypoint(
            0.25, hip_y, confidence
        )
        points[CocoKeypoint.RIGHT_SHOULDER] = Keypoint(
            0.35, hip_y, confidence
        )
        points[CocoKeypoint.LEFT_HIP] = Keypoint(0.45, hip_y, confidence)
        points[CocoKeypoint.RIGHT_HIP] = Keypoint(0.55, hip_y, confidence)
        box = BoundingBox(0.15, hip_y - 0.1, 0.85, hip_y + 0.1)
    else:
        points[CocoKeypoint.LEFT_SHOULDER] = Keypoint(
            0.45, hip_y - 0.2, confidence
        )
        points[CocoKeypoint.RIGHT_SHOULDER] = Keypoint(
            0.55, hip_y - 0.2, confidence
        )
        points[CocoKeypoint.LEFT_HIP] = Keypoint(0.47, hip_y, confidence)
        points[CocoKeypoint.RIGHT_HIP] = Keypoint(0.53, hip_y, confidence)
        box = BoundingBox(0.4, hip_y - 0.4, 0.6, hip_y + 0.3)
    return PoseObservation(timestamp, tuple(points), box, track_id)


def test_detector_confirms_rapid_descent_and_persistent_low_posture():
    detector = RuleBasedFallDetector()

    detector.update(observation(0.0, 0.40))
    candidate = detector.update(observation(0.4, 0.58))
    possible = detector.update(observation(0.5, 0.70, horizontal=True))
    confirmed = detector.update(observation(1.3, 0.72, horizontal=True))

    assert candidate.transition is DetectorTransition.CANDIDATE_STARTED
    assert possible.state is DetectorState.POSSIBLE_FALL
    assert confirmed.state is DetectorState.FALLEN
    assert confirmed.transition is DetectorTransition.FALL_CONFIRMED
    assert confirmed.proposal is not None
    assert confirmed.proposal.started_at_s == 0.0
    assert confirmed.proposal.confirmed_at_s == 1.3
    assert confirmed.proposal.track_id == 7


def test_detector_does_not_flag_slow_intentional_lying():
    detector = RuleBasedFallDetector()

    outputs = [
        detector.update(observation(0.0, 0.40)),
        detector.update(observation(1.0, 0.50)),
        detector.update(observation(2.0, 0.62, horizontal=True)),
        detector.update(observation(3.0, 0.70, horizontal=True)),
    ]

    assert all(output.state is DetectorState.MONITORING for output in outputs)
    assert all(
        output.transition is DetectorTransition.NONE for output in outputs
    )


def test_detector_cancels_descent_without_low_horizontal_posture():
    config = FallRulesConfig(candidate_timeout_seconds=1.0)
    detector = RuleBasedFallDetector(config)

    detector.update(observation(0.0, 0.40))
    candidate = detector.update(observation(0.4, 0.58))
    cancelled = detector.update(observation(1.1, 0.50))

    assert candidate.state is DetectorState.DESCENDING
    assert cancelled.state is DetectorState.MONITORING
    assert cancelled.transition is DetectorTransition.CANDIDATE_CANCELLED


def test_detector_reports_recovery_after_confirmed_fall():
    detector = RuleBasedFallDetector()
    detector.update(observation(0.0, 0.40))
    detector.update(observation(0.4, 0.58))
    detector.update(observation(0.5, 0.70, horizontal=True))
    detector.update(observation(1.3, 0.72, horizontal=True))

    detector.update(observation(2.0, 0.45))
    recovered = detector.update(observation(2.7, 0.44))

    assert recovered.state is DetectorState.MONITORING
    assert recovered.transition is DetectorTransition.RECOVERED


def test_detector_resets_candidate_after_pose_is_missing():
    detector = RuleBasedFallDetector()
    detector.update(observation(0.0, 0.40))
    detector.update(observation(0.4, 0.58))

    detector.update_missing(0.5)
    lost = detector.update_missing(1.0)

    assert lost.state is DetectorState.MONITORING
    assert lost.transition is DetectorTransition.TRACK_LOST


def test_detector_rejects_low_confidence_core_keypoints():
    detector = RuleBasedFallDetector()

    output = detector.update(observation(0.0, 0.4, confidence=0.1))

    assert output.features is None
    assert output.state is DetectorState.MONITORING


def test_repeated_low_confidence_poses_eventually_reset_candidate():
    detector = RuleBasedFallDetector()
    detector.update(observation(0.0, 0.40))
    detector.update(observation(0.4, 0.58))

    detector.update(observation(0.5, 0.6, confidence=0.1))
    lost = detector.update(observation(1.0, 0.6, confidence=0.1))

    assert lost.state is DetectorState.MONITORING
    assert lost.transition is DetectorTransition.TRACK_LOST


def test_detector_rejects_backwards_timestamps():
    detector = RuleBasedFallDetector()
    detector.update(observation(1.0, 0.4))

    try:
        detector.update(observation(0.9, 0.4))
    except ValueError as exc:
        assert "monotonically increasing" in str(exc)
    else:
        raise AssertionError("backwards timestamp was accepted")
