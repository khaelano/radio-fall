"""Temporal, rule-based fall proposals derived from pose landmarks."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum, IntEnum
from math import atan2, degrees, hypot, isfinite
from pathlib import Path
from statistics import median
import tomllib


class CocoKeypoint(IntEnum):
    """Indices emitted by a COCO-compatible YOLO pose model."""

    NOSE = 0
    LEFT_EYE = 1
    RIGHT_EYE = 2
    LEFT_EAR = 3
    RIGHT_EAR = 4
    LEFT_SHOULDER = 5
    RIGHT_SHOULDER = 6
    LEFT_ELBOW = 7
    RIGHT_ELBOW = 8
    LEFT_WRIST = 9
    RIGHT_WRIST = 10
    LEFT_HIP = 11
    RIGHT_HIP = 12
    LEFT_KNEE = 13
    RIGHT_KNEE = 14
    LEFT_ANKLE = 15
    RIGHT_ANKLE = 16


@dataclass(frozen=True)
class Keypoint:
    """One normalized image-space keypoint."""

    x: float
    y: float
    confidence: float


@dataclass(frozen=True)
class BoundingBox:
    """A normalized person bounding box."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def aspect_ratio(self) -> float:
        """Return width divided by height."""

        return max(0.0, self.x_max - self.x_min) / max(
            1e-6, self.y_max - self.y_min
        )


@dataclass(frozen=True)
class PoseObservation:
    """One timestamped pose for a selected person."""

    timestamp_s: float
    keypoints: tuple[Keypoint, ...]
    box: BoundingBox
    track_id: int | None = None

    def __post_init__(self) -> None:
        if not isfinite(self.timestamp_s):
            raise ValueError("timestamp_s must be finite")
        if len(self.keypoints) < len(CocoKeypoint):
            raise ValueError("a COCO pose observation needs 17 keypoints")


@dataclass(frozen=True)
class FallRulesConfig:
    """Thresholds for converting pose motion into fall proposals."""

    history_seconds: float = 2.0
    descent_window_seconds: float = 0.8
    min_descent_duration_seconds: float = 0.1
    min_hip_drop_torso_lengths: float = 0.75
    min_hip_speed_torso_lengths_per_second: float = 1.2
    min_torso_angle_degrees: float = 55.0
    min_horizontal_box_ratio: float = 0.9
    min_low_hip_y: float = 0.58
    confirmation_seconds: float = 0.8
    candidate_timeout_seconds: float = 2.0
    recovery_seconds: float = 0.6
    recovery_torso_angle_degrees: float = 35.0
    recovery_box_ratio: float = 0.75
    max_missing_seconds: float = 0.5
    min_keypoint_confidence: float = 0.35

    @classmethod
    def from_toml(cls, path: Path) -> FallRulesConfig:
        """Load the ``fall_detection`` table from a TOML file."""

        with path.open("rb") as config_file:
            document = tomllib.load(config_file)
        values = document.get("fall_detection")
        if not isinstance(values, dict):
            raise ValueError("config must contain a [fall_detection] table")
        return cls(**values)


class DetectorState(str, Enum):
    """Persistent state of the temporal detector."""

    MONITORING = "monitoring"
    DESCENDING = "descending"
    POSSIBLE_FALL = "possible_fall"
    FALLEN = "fallen"


class DetectorTransition(str, Enum):
    """A noteworthy state change produced by an update."""

    NONE = "none"
    CANDIDATE_STARTED = "candidate_started"
    CANDIDATE_CANCELLED = "candidate_cancelled"
    FALL_CONFIRMED = "fall_confirmed"
    RECOVERED = "recovered"
    TRACK_LOST = "track_lost"


@dataclass(frozen=True)
class PoseFeatures:
    """Interpretable features calculated for one pose."""

    timestamp_s: float
    hip_y: float
    torso_length: float
    torso_angle_degrees: float
    box_aspect_ratio: float
    hip_drop_torso_lengths: float
    hip_speed_torso_lengths_per_second: float
    rapid_descent: bool
    horizontal_posture: bool
    low_posture: bool


@dataclass(frozen=True)
class FallEventProposal:
    """A suggested event interval that still requires human review."""

    started_at_s: float
    confirmed_at_s: float
    track_id: int | None


@dataclass(frozen=True)
class DetectionOutput:
    """Result returned for every observation or missing-frame update."""

    state: DetectorState
    transition: DetectorTransition = DetectorTransition.NONE
    features: PoseFeatures | None = None
    proposal: FallEventProposal | None = None


@dataclass(frozen=True)
class _CorePose:
    timestamp_s: float
    hip_x: float
    hip_y: float
    torso_length: float
    torso_angle_degrees: float
    box_aspect_ratio: float


def _midpoint(
    first: Keypoint,
    second: Keypoint,
    minimum_confidence: float,
) -> tuple[float, float] | None:
    if (
        first.confidence < minimum_confidence
        or second.confidence < minimum_confidence
    ):
        return None
    return ((first.x + second.x) / 2.0, (first.y + second.y) / 2.0)


class RuleBasedFallDetector:
    """Propose fall intervals from rapid descent and persistent low posture.

    The detector intentionally produces reviewable proposals rather than
    ground-truth labels. Coordinates are expected to be normalized to the
    source frame, with image-space ``y`` increasing downwards.
    """

    def __init__(self, config: FallRulesConfig | None = None) -> None:
        self.config = config or FallRulesConfig()
        self.state = DetectorState.MONITORING
        self._history: deque[_CorePose] = deque()
        self._candidate_started_at: float | None = None
        self._candidate_track_id: int | None = None
        self._low_started_at: float | None = None
        self._recovery_started_at: float | None = None
        self._missing_started_at: float | None = None
        self._last_timestamp: float | None = None

    def reset(self) -> None:
        """Clear temporal state and begin monitoring a new sequence."""

        self.state = DetectorState.MONITORING
        self._history.clear()
        self._candidate_started_at = None
        self._candidate_track_id = None
        self._low_started_at = None
        self._recovery_started_at = None
        self._missing_started_at = None
        self._last_timestamp = None

    def update(self, observation: PoseObservation) -> DetectionOutput:
        """Process one timestamped pose observation."""

        self._check_timestamp(observation.timestamp_s)
        core = self._extract_core_pose(observation)
        if core is None:
            return self.update_missing(observation.timestamp_s, checked=True)

        self._missing_started_at = None
        self._append_history(core)
        features, descent_start = self._calculate_features(core)
        transition = DetectorTransition.NONE
        proposal = None

        if self.state is DetectorState.MONITORING and features.rapid_descent:
            self._candidate_started_at = descent_start
            self._candidate_track_id = observation.track_id
            transition = DetectorTransition.CANDIDATE_STARTED
            if features.horizontal_posture:
                self.state = DetectorState.POSSIBLE_FALL
                self._low_started_at = (
                    observation.timestamp_s if features.low_posture else None
                )
            else:
                self.state = DetectorState.DESCENDING

        elif self.state is DetectorState.DESCENDING:
            if features.horizontal_posture:
                self.state = DetectorState.POSSIBLE_FALL
                self._low_started_at = (
                    observation.timestamp_s if features.low_posture else None
                )
            elif self._candidate_timed_out(observation.timestamp_s):
                self._cancel_candidate()
                transition = DetectorTransition.CANDIDATE_CANCELLED

        elif self.state is DetectorState.POSSIBLE_FALL:
            if features.low_posture:
                if self._low_started_at is None:
                    self._low_started_at = observation.timestamp_s
                low_duration = observation.timestamp_s - self._low_started_at
                if low_duration >= self.config.confirmation_seconds:
                    self.state = DetectorState.FALLEN
                    transition = DetectorTransition.FALL_CONFIRMED
                    proposal = FallEventProposal(
                        started_at_s=self._candidate_started_at
                        if self._candidate_started_at is not None
                        else observation.timestamp_s,
                        confirmed_at_s=observation.timestamp_s,
                        track_id=self._candidate_track_id,
                    )
            else:
                self._low_started_at = None
                if self._candidate_timed_out(observation.timestamp_s):
                    self._cancel_candidate()
                    transition = DetectorTransition.CANDIDATE_CANCELLED

        elif self.state is DetectorState.FALLEN:
            recovered = (
                features.torso_angle_degrees
                <= self.config.recovery_torso_angle_degrees
                and features.box_aspect_ratio
                <= self.config.recovery_box_ratio
                and features.hip_y < self.config.min_low_hip_y
            )
            if recovered:
                if self._recovery_started_at is None:
                    self._recovery_started_at = observation.timestamp_s
                recovery_duration = (
                    observation.timestamp_s - self._recovery_started_at
                )
                if recovery_duration >= self.config.recovery_seconds:
                    self._clear_event(keep_history=True)
                    transition = DetectorTransition.RECOVERED
            else:
                self._recovery_started_at = None

        return DetectionOutput(self.state, transition, features, proposal)

    def update_missing(
        self, timestamp_s: float, *, checked: bool = False
    ) -> DetectionOutput:
        """Advance time when no sufficiently reliable pose is available."""

        if not checked:
            self._check_timestamp(timestamp_s)
        if self._missing_started_at is None:
            self._missing_started_at = timestamp_s
        missing_duration = timestamp_s - self._missing_started_at
        if (
            missing_duration >= self.config.max_missing_seconds
            and self.state is not DetectorState.MONITORING
        ):
            self._clear_event(keep_history=False)
            return DetectionOutput(
                self.state, DetectorTransition.TRACK_LOST
            )
        return DetectionOutput(self.state)

    def _check_timestamp(self, timestamp_s: float) -> None:
        if not isfinite(timestamp_s):
            raise ValueError("timestamp must be finite")
        if self._last_timestamp is not None and timestamp_s < self._last_timestamp:
            raise ValueError("timestamps must be monotonically increasing")
        self._last_timestamp = timestamp_s

    def _extract_core_pose(self, observation: PoseObservation) -> _CorePose | None:
        minimum = self.config.min_keypoint_confidence
        left_shoulder = observation.keypoints[CocoKeypoint.LEFT_SHOULDER]
        right_shoulder = observation.keypoints[CocoKeypoint.RIGHT_SHOULDER]
        left_hip = observation.keypoints[CocoKeypoint.LEFT_HIP]
        right_hip = observation.keypoints[CocoKeypoint.RIGHT_HIP]
        shoulders = _midpoint(left_shoulder, right_shoulder, minimum)
        hips = _midpoint(left_hip, right_hip, minimum)
        if shoulders is None or hips is None:
            return None
        delta_x = shoulders[0] - hips[0]
        delta_y = shoulders[1] - hips[1]
        torso_length = hypot(delta_x, delta_y)
        if torso_length < 1e-3:
            return None
        angle = degrees(atan2(abs(delta_x), abs(delta_y)))
        return _CorePose(
            timestamp_s=observation.timestamp_s,
            hip_x=hips[0],
            hip_y=hips[1],
            torso_length=torso_length,
            torso_angle_degrees=angle,
            box_aspect_ratio=observation.box.aspect_ratio,
        )

    def _append_history(self, pose: _CorePose) -> None:
        self._history.append(pose)
        cutoff = pose.timestamp_s - self.config.history_seconds
        while self._history and self._history[0].timestamp_s < cutoff:
            self._history.popleft()

    def _calculate_features(
        self, current: _CorePose
    ) -> tuple[PoseFeatures, float]:
        candidates = [
            previous
            for previous in self._history
            if self.config.min_descent_duration_seconds
            <= current.timestamp_s - previous.timestamp_s
            <= self.config.descent_window_seconds
        ]
        best_drop = 0.0
        best_speed = 0.0
        descent_start = current.timestamp_s
        if candidates:
            torso_scale = median(
                [pose.torso_length for pose in candidates] + [current.torso_length]
            )
            for previous in candidates:
                duration = current.timestamp_s - previous.timestamp_s
                drop = (current.hip_y - previous.hip_y) / max(
                    torso_scale, 1e-3
                )
                speed = drop / duration
                if drop > best_drop:
                    best_drop = drop
                    best_speed = speed
                    descent_start = previous.timestamp_s

        rapid_descent = (
            best_drop >= self.config.min_hip_drop_torso_lengths
            and best_speed
            >= self.config.min_hip_speed_torso_lengths_per_second
        )
        horizontal = (
            current.torso_angle_degrees
            >= self.config.min_torso_angle_degrees
            or current.box_aspect_ratio
            >= self.config.min_horizontal_box_ratio
        )
        low = horizontal and current.hip_y >= self.config.min_low_hip_y
        return (
            PoseFeatures(
                timestamp_s=current.timestamp_s,
                hip_y=current.hip_y,
                torso_length=current.torso_length,
                torso_angle_degrees=current.torso_angle_degrees,
                box_aspect_ratio=current.box_aspect_ratio,
                hip_drop_torso_lengths=best_drop,
                hip_speed_torso_lengths_per_second=best_speed,
                rapid_descent=rapid_descent,
                horizontal_posture=horizontal,
                low_posture=low,
            ),
            descent_start,
        )

    def _candidate_timed_out(self, timestamp_s: float) -> bool:
        return (
            self._candidate_started_at is not None
            and timestamp_s - self._candidate_started_at
            >= self.config.candidate_timeout_seconds
        )

    def _cancel_candidate(self) -> None:
        self._clear_event(keep_history=True)

    def _clear_event(self, *, keep_history: bool) -> None:
        self.state = DetectorState.MONITORING
        self._candidate_started_at = None
        self._candidate_track_id = None
        self._low_started_at = None
        self._recovery_started_at = None
        self._missing_started_at = None
        if not keep_history:
            self._history.clear()
